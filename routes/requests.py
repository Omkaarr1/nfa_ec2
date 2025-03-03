from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import json, os
import schemas, crud, models, auth, utils
from database import get_db
from starlette.responses import StreamingResponse
router = APIRouter()

@router.post("/requests/{request_id}/edit", response_model=schemas.RequestResponse)
async def edit_request(
    request_id: int,
    subject: str = Form(...),
    description: str = Form(...),
    area: str = Form(...),
    project: str = Form(...),
    tower: str = Form(...),
    department: str = Form(...),
    references: str = Form(...),
    priority: str = Form(...),
    approvers: str = Form(...),
    files: Optional[List[UploadFile]] = File(None),
    current_user: models.User = Depends(lambda token=Depends(auth.oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)),
    db: Session = Depends(get_db)
):
    req = crud.get_request_by_id(db, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "NEW":
        raise HTTPException(status_code=400, detail="Only NEW requests can be edited.")
    if req.initiator_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not allowed to edit this request")
    try:
        approvers_list = json.loads(approvers)
        approvers_list = [x for x in approvers_list if x != req.supervisor_id]
        if not isinstance(approvers_list, list) or not all(isinstance(x, int) for x in approvers_list):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="Approvers must be a JSON list of user IDs.")
    current_time = datetime.utcnow()
    req.subject = subject
    req.description = description
    req.area = area
    req.project = project
    req.tower = tower
    req.department = department
    req.references = references
    req.priority = priority
    req.approvers = approvers_list
    req.updated_at = current_time
    req.last_action = f"Request edited at {current_time.strftime('%d-%m-%Y %H:%M')}"
    crud.delete_approver_actions_by_request(db, req.id)
    if files:
        if not req.files:
            req.files = []
        for file in files:
            file.file.seek(0)
            content = await file.read()
            timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            new_filename = f"{req.id}_{timestamp}"
            ext = file.filename.split('.')[-1] if file.filename and '.' in file.filename else ''
            if ext:
                new_filename += f".{ext}"
            file_location = os.path.join(utils.UPLOAD_FOLDER, new_filename)
            with open(file_location, "wb") as f:
                f.write(content)
            file_record = {"file_url": f"/files/{new_filename}", "file_display_name": file.filename}
            req.files.append(file_record)
    crud.update_request(db, req)
    response_data = utils.to_request_response(db, req)
    return response_data

@router.post("/requests/review", response_model=schemas.RequestResponse)
async def review_request(action: schemas.ApprovalAction, current_user: models.User = Depends(lambda token=Depends(auth.oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)), db: Session = Depends(get_db)):
    req = crud.get_request_by_id(db, action.request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found.")
    if req.status in ("APPROVED", "REJECTED"):
        raise HTTPException(status_code=400, detail=f"Request is already {req.status} and cannot be changed.")
    current_time = datetime.utcnow()
    if req.status == "NEW":
        if current_user.id != req.supervisor_id and not (2 in current_user.role or 3 in current_user.role):
            raise HTTPException(status_code=403, detail="Not authorized to approve/reject at supervisor stage.")
        req.supervisor_approved = action.approved
        req.supervisor_comment = action.comment
        req.supervisor_approved_at = current_time
        req.updated_at = current_time
        if action.approved:
            if req.approvers:
                req.status = "IN_PROGRESS"
                req.last_action = f"Supervisor approved at {current_time.strftime('%d-%m-%Y %H:%M')}"
                req.current_approver_index = 0
            else:
                req.status = "APPROVED"
                req.last_action = f"Supervisor approved at {current_time.strftime('%d-%m-%Y %H:%M')}. No further approvers – request is fully approved."
        else:
            req.status = "REJECTED"
            req.last_action = f"Supervisor rejected at {current_time.strftime('%d-%m-%Y %H:%M')}"
        crud.update_request(db, req)
        return utils.to_request_response(db, req)
    if req.status == "IN_PROGRESS":
        if req.current_approver_index >= len(req.approvers):
            raise HTTPException(status_code=400, detail="No further approver action is pending for this request.")
        expected_approver_id = req.approvers[req.current_approver_index]
        if current_user.id != expected_approver_id and not (2 in current_user.role or 3 in current_user.role):
            raise HTTPException(status_code=403, detail="Not authorized to approve this pending stage.")
        existing_action = crud.get_approver_action(db, req.id, expected_approver_id)
        if existing_action:
            raise HTTPException(status_code=400, detail="You have already taken action on this request.")
        if (2 in current_user.role or 3 in current_user.role) and current_user.id != expected_approver_id:
            new_action = {
                "request_id": req.id,
                "approver_id": current_user.id,
                "approved": "APPROVED" if action.approved else "REJECTED",
                "received_at": current_time.strftime("%d-%m-%Y %H:%M"),
                "action_time": current_time.strftime("%d-%m-%Y %H:%M"),
                "comment": action.comment,
                "approved_by": current_user.name
            }
            req.last_action = f"Approved by {current_user.name} at {current_time.strftime('%d-%m-%Y %H:%M')}"
        else:
            new_action = {
                "request_id": req.id,
                "approver_id": expected_approver_id,
                "approved": "APPROVED" if action.approved else "REJECTED",
                "received_at": current_time.strftime("%d-%m-%Y %H:%M"),
                "action_time": current_time.strftime("%d-%m-%Y %H:%M"),
                "comment": action.comment
            }
            req.last_action = f"Approver {expected_approver_id} approved at {current_time.strftime('%d-%m-%Y %H:%M')}"
        crud.create_approver_action(db, new_action)
        req.updated_at = current_time
        if action.approved:
            req.current_approver_index += 1
            if req.current_approver_index >= len(req.approvers):
                req.status = "APPROVED"
                req.last_action += ". All approvals are completed."
            else:
                next_approver_id = req.approvers[req.current_approver_index]
                req.last_action += f". Next approver is user {next_approver_id}."
        else:
            req.status = "REJECTED"
            req.last_action = f"Approver action rejected at {current_time.strftime('%d-%m-%Y %H:%M')}"
        crud.update_request(db, req)
        return utils.to_request_response(db, req)
    raise HTTPException(status_code=400, detail="Request cannot be approved or rejected in its current state.")

@router.post("/requests/", response_model=schemas.RequestResponse)
async def create_new_request(
    supervisor_id: int = Form(...),
    subject: str = Form(...),
    description: str = Form(...),
    area: str = Form(...),
    project: str = Form(...),
    tower: str = Form(...),
    department: str = Form(...),
    references: str = Form(""),
    priority: str = Form("Low"),
    approvers: str = Form(...),
    files: Optional[List[UploadFile]] = File(None),
    current_user: models.User = Depends(
        lambda token=Depends(auth.oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)
    ),
    db: Session = Depends(get_db)
):
    """
    Create (raise) a brand-new NFA request.
    """
    # 1) Validate and parse 'approvers' as a JSON list of user IDs
    try:
        approvers_list = json.loads(approvers)
        # remove the supervisor from the approver list, if desired:
        approvers_list = [u for u in approvers_list if u != supervisor_id]

        # must be a list of ints
        if not isinstance(approvers_list, list) or not all(isinstance(x, int) for x in approvers_list):
            raise ValueError("Approvers must be a JSON list of user IDs.")
    except:
        raise HTTPException(status_code=400, detail="Approvers must be a JSON list of user IDs.")

    # 2) Build the request data
    current_time = datetime.utcnow()
    new_req_data = {
        "initiator_id": current_user.id,
        "supervisor_id": supervisor_id,
        "subject": subject,
        "description": description,
        "area": area,
        "project": project,
        "tower": tower,
        "department": department,
        "references": references,
        "priority": priority,
        "approvers": approvers_list,
        "current_approver_index": 0,
        "status": "NEW",
        "created_at": current_time,
        "updated_at": current_time,
        "last_action": f"Request created at {current_time.strftime('%d-%m-%Y %H:%M')}",
    }

    # 3) Create the request in DB
    new_req = crud.create_request(db, new_req_data)

    # 4) Handle files (if any)
    if files:
        file_records = []
        for file in files:
            file.file.seek(0)
            content = await file.read()
            timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            new_filename = f"{new_req.id}_{timestamp}"
            ext = ""
            if file.filename and "." in file.filename:
                ext = file.filename.split(".")[-1]
            if ext:
                new_filename += f".{ext}"

            file_location = os.path.join(utils.UPLOAD_FOLDER, new_filename)
            with open(file_location, "wb") as f:
                f.write(content)

            file_record = {
                "file_url": f"/files/{new_filename}",
                "file_display_name": file.filename
            }
            file_records.append(file_record)

        new_req.files = file_records
        crud.update_request(db, new_req)

    # 5) Return the newly created request as a response
    return utils.to_request_response(db, new_req)


@router.get("/requests/", response_model=List[schemas.RequestResponse])
async def list_requests(
    note_id: Optional[int] = None,
    date: Optional[str] = None,
    initiator: Optional[str] = None,
    filter: Optional[str] = None,
    current_user: models.User = Depends(lambda token=Depends(auth.oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)),
    db: Session = Depends(get_db)
):
    all_requests = crud.list_all_requests(db)
    if note_id:
        all_requests = [r for r in all_requests if r.id == note_id]
    if date:
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            next_day = date_obj + timedelta(days=1)
            def within_date(r):
                return date_obj <= r.created_at < next_day
            all_requests = [r for r in all_requests if within_date(r)]
        except ValueError:
            raise HTTPException(status_code=400, detail="Date must be in YYYY-MM-DD format")
    if initiator:
        def match_initiator(r):
            user_ = crud.get_user_by_id(db, r.initiator_id)
            return user_ and initiator.lower() in user_.name.lower()
        all_requests = [r for r in all_requests if match_initiator(r)]
    if filter:
        f = filter.upper()
        if f == "PENDING":
            all_requests = [r for r in all_requests if r.status in ("NEW", "IN_PROGRESS")]
        elif f == "APPROVED":
            all_requests = [r for r in all_requests if r.status == "APPROVED"]
    visible = []
    for r in all_requests:
        if (current_user.id == r.initiator_id or current_user.id == r.supervisor_id or 
            (r.status in ("APPROVED", "REJECTED") and current_user.id in r.approvers) or 
            (r.status == "IN_PROGRESS" and r.current_approver_index < len(r.approvers) and current_user.id == r.approvers[r.current_approver_index])):
            visible.append(r)
    responses = [utils.to_request_response(db, r) for r in visible]
    return responses

@router.get("/requests/{request_id}/pdf")
async def download_pdf(
    request_id: int,
    request: Request,
    access_token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    # 1) Extract token
    token = access_token
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # 2) Verify current user
    current_user = auth.get_current_user(token, db)

    # 3) Find the request
    req = crud.get_request_by_id(db, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="NFA not found")

    # 4) Only allowed if request is fully approved
    if req.status != "APPROVED":
        raise HTTPException(
            status_code=400,
            detail="PDF can only be downloaded for approved NFAs."
        )

    # 5) Must be initiator or have admin-type role
    if current_user.id != req.initiator_id and not (2 in current_user.role or 3 in current_user.role):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to download this PDF"
        )

    # 6) Generate or retrieve the PDF
    pdf_buffer = utils.generate_pdf(db, req)  # expects a BytesIO

    # IMPORTANT: reset pointer before streaming
    pdf_buffer.seek(0)

    # 7) Return as an attachment for better cross-platform support
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="nfa_{req.id}.pdf"'
        },
    )

@router.post("/upload-file/{request_id}")
async def upload_files_for_request(
    request_id: int,
    files: Optional[List[UploadFile]] = File(None),
    current_user: models.User = Depends(lambda token=Depends(auth.oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)),
    db: Session = Depends(get_db)
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    req = crud.get_request_by_id(db, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.initiator_id != current_user.id and 2 not in current_user.role:
        raise HTTPException(status_code=403, detail="Not authorized to upload files for this request")
    file_records = req.files if req.files else []
    for file in files:
        original_filename = file.filename or "unnamed_file"
        sanitized_filename = original_filename.replace(" ", "_")
        ext = sanitized_filename.split('.')[-1].lower() if '.' in sanitized_filename else ''
        subfolder = "others"
        if ext == "pdf":
            subfolder = "pdf"
        elif ext in ["jpg", "jpeg", "png", "gif", "bmp"]:
            subfolder = "image"
        subfolder_path = os.path.join(utils.UPLOAD_FOLDER, subfolder)
        os.makedirs(subfolder_path, exist_ok=True)
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        new_filename = f"{request_id}_{timestamp}_{sanitized_filename}"
        file_location = os.path.join(subfolder_path, new_filename)
        file.file.seek(0)
        content = await file.read()
        with open(file_location, "wb") as f:
            f.write(content)
        file_record = {"file_url": f"/files/{subfolder}/{new_filename}", "file_display_name": original_filename}
        file_records.append(file_record)
    req.files = file_records
    crud.update_request(db, req)
    return {"files": req.files}

@router.post("/requests/reinitiate", response_model=schemas.RequestResponse)
async def reinitiate_request(
    request_id: int,
    edit_details: bool = Form(False),
    subject: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    area: Optional[str] = Form(None),
    project: Optional[str] = Form(None),
    tower: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    references: Optional[str] = Form(None),
    priority: Optional[str] = Form(None),
    approvers: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    current_user: models.User = Depends(lambda token=Depends(auth.oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)),
    db: Session = Depends(get_db)
):
    req = crud.get_request_by_id(db, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.initiator_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not allowed to reinitiate this request")
    if req.status != "REJECTED":
        raise HTTPException(status_code=400, detail="Only declined (REJECTED) requests can be re-initiated.")
    current_time = datetime.utcnow()
    if edit_details:
        if not (subject and description and area and project and tower and department and references and priority and approvers):
            raise HTTPException(status_code=400, detail="All fields are required for editing details.")
        try:
            approvers_list = json.loads(approvers)
            approvers_list = [x for x in approvers_list if x != req.supervisor_id]
            if not isinstance(approvers_list, list) or not all(isinstance(x, int) for x in approvers_list):
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="Approvers must be a JSON list of user IDs.")
        req.subject = subject
        req.description = description
        req.area = area
        req.project = project
        req.tower = tower
        req.department = department
        req.references = references
        req.priority = priority
        req.approvers = approvers_list
        req.status = "NEW"
        req.current_approver_index = 0
        req.supervisor_approved = None
        req.supervisor_approved_at = None
        req.supervisor_comment = None
        req.last_action = f"Request re-initiated at {current_time.strftime('%d-%m-%Y %H:%M')}"
        crud.delete_approver_actions_by_request(db, req.id)
        if files:
            if not req.files:
                req.files = []
            for file in files:
                file.file.seek(0)
                content = await file.read()
                timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
                new_filename = f"{req.id}_{timestamp}"
                ext = file.filename.split('.')[-1] if file.filename and '.' in file.filename else ''
                if ext:
                    new_filename += f".{ext}"
                file_location = os.path.join(utils.UPLOAD_FOLDER, new_filename)
                with open(file_location, "wb") as f:
                    f.write(content)
                file_record = {"file_url": f"/files/{new_filename}", "file_display_name": file.filename}
                req.files.append(file_record)
        req.updated_at = current_time
        crud.update_request(db, req)
        return utils.to_request_response(db, req)
    else:
        new_req_data = {
            "initiator_id": req.initiator_id,
            "supervisor_id": req.supervisor_id,
            "subject": req.subject,
            "description": req.description,
            "area": req.area,
            "project": req.project,
            "tower": req.tower,
            "department": req.department,
            "references": req.references,
            "priority": req.priority,
            "approvers": req.approvers,
            "current_approver_index": 0,
            "status": "NEW",
            "created_at": current_time,
            "updated_at": current_time,
            "last_action": f"Request re-initiated at {current_time.strftime('%d-%m-%Y %H:%M')}",
            "supervisor_approved_at": None,
            "supervisor_approved": None,
            "supervisor_comment": None,
            "files": []
        }
        if subject and description and area and project and tower and department and references and priority and approvers:
            try:
                approvers_list = json.loads(approvers)
                approvers_list = [x for x in approvers_list if x != req.supervisor_id]
                if not isinstance(approvers_list, list) or not all(isinstance(x, int) for x in approvers_list):
                    raise ValueError
            except ValueError:
                raise HTTPException(status_code=400, detail="Approvers must be a JSON list of user IDs.")
            new_req_data["subject"] = subject
            new_req_data["description"] = description
            new_req_data["area"] = area
            new_req_data["project"] = project
            new_req_data["tower"] = tower
            new_req_data["department"] = department
            new_req_data["references"] = references
            new_req_data["priority"] = priority
            new_req_data["approvers"] = approvers_list
        new_req = crud.create_request(db, new_req_data)
        if files:
            file_records = []
            for file in files:
                file.file.seek(0)
                content = await file.read()
                timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
                new_filename = f"{new_req.id}_{timestamp}"
                ext = file.filename.split('.')[-1] if file.filename and '.' in file.filename else ''
                if ext:
                    new_filename += f".{ext}"
                file_location = os.path.join(utils.UPLOAD_FOLDER, new_filename)
                with open(file_location, "wb") as f:
                    f.write(content)
                file_record = {"file_url": f"/files/{new_filename}", "file_display_name": file.filename}
                file_records.append(file_record)
            new_req.files = file_records
            crud.update_request(db, new_req)
        return utils.to_request_response(db, new_req)

@router.delete("/requests/{request_id}/withdraw")
async def withdraw_request(request_id: int, current_user: models.User = Depends(lambda token=Depends(auth.oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)), db: Session = Depends(get_db)):
    req = crud.get_request_by_id(db, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "NEW":
        raise HTTPException(status_code=400, detail="Only NEW requests can be withdrawn")
    db.delete(req)
    db.commit()
    return {"detail": "NFA withdrawn successfully"}
