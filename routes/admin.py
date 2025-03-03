from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import os, json
import schemas, crud, models, auth, utils
from database import get_db

router = APIRouter(prefix="/admin", tags=["admin"])

def get_admin_user(current_user: models.User = Depends(lambda token=Depends(auth.oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db))):
    if 2 not in current_user.role and 3 not in current_user.role:
        raise HTTPException(status_code=403, detail="Admin privileges required.")
    return current_user

@router.get("/total-requests")
def total_requests(admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    total = len(crud.list_all_requests(db))
    return {"total_requests": total}

@router.get("/pending-requests")
def pending_requests(admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    all_requests = crud.list_all_requests(db)
    pending = [r for r in all_requests if r.status in ("NEW", "IN_PROGRESS")]
    return {"total_pending_requests": len(pending)}

@router.get("/users", response_model=List[schemas.UserResponse])
def admin_view_all_users(admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    return crud.list_all_users(db)

@router.put("/users/{user_id}", response_model=schemas.UserResponse)
def admin_edit_user(user_id: int, user_edit: schemas.AdminEditUser, admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user_edit.username:
        user.username = user_edit.username
    if user_edit.password:
        user.hashed_password = auth.get_password_hash(user_edit.password)
    if user_edit.name:
        user.name = user_edit.name
    if user_edit.role is not None:
        user.role = user_edit.role
    if user_edit.email is not None:
        user.email = user_edit.email
    crud.update_user(db, user)
    return user

@router.post("/users", response_model=schemas.UserResponse)
def admin_create_user(user_data: schemas.AdminCreateUser, admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    if crud.get_user_by_username(db, user_data.username):
        raise HTTPException(status_code=400, detail="User with this username already exists.")
    hashed_password = auth.get_password_hash(user_data.password)
    new_user = crud.create_user(db, user_data, hashed_password)
    return new_user

@router.delete("/users/{user_id}")
def admin_delete_user(user_id: int, admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"detail": f"User {user_id} deleted successfully."}

@router.get("/users/pending-requests")
def pending_requests_per_user(admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    users = crud.list_all_users(db)
    all_requests = crud.list_all_requests(db)
    results = []
    for user in users:
        pending = [r for r in all_requests if r.initiator_id == user.id and r.status in ("NEW", "IN_PROGRESS")]
        results.append({"user_id": user.id, "pending_requests": len(pending)})
    return results

@router.post("/requests/{request_id}/approve")
def admin_approve_request(request_id: int, admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    req = crud.get_request_by_id(db, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    current_time = datetime.utcnow()
    req.status = "Approved by ADMIN"
    req.last_action = f"Approved by ADMIN at {current_time.strftime('%d-%m-%Y %H:%M')}"
    req.updated_at = current_time
    crud.update_request(db, req)
    return {"detail": f"Request {request_id} approved by ADMIN."}

@router.get("/users/{user_id}/files")
def admin_view_user_files(user_id: int, admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    user_requests = [r for r in crud.list_all_requests(db) if r.initiator_id == user_id]
    files = []
    for req in user_requests:
        if req.files:
            files.extend(req.files)
    return {"user_id": user_id, "files": files}

@router.delete("/requests/{request_id}/files")
def delete_request_file(request_id: int, file_url: str, current_user: models.User = Depends(lambda token=Depends(auth.oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)), db: Session = Depends(get_db)):
    if 2 not in current_user.role and 3 not in current_user.role:
        raise HTTPException(status_code=403, detail="Not authorized to delete files")
    req = crud.get_request_by_id(db, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if not req.files:
        raise HTTPException(status_code=404, detail="No files associated with this request")
    normalized_input_url = utils.normalize_url(file_url)
    original_files = req.files
    updated_files = [file for file in original_files if utils.normalize_url(file.get("file_url", "")) != normalized_input_url]
    if len(updated_files) == len(original_files):
        raise HTTPException(status_code=404, detail="File not found in the request")
    req.files = updated_files
    crud.update_request(db, req)
    if file_url.startswith("/files/"):
        relative_path = file_url[len("/files/"):]
    else:
        relative_path = os.path.basename(file_url)
    file_path = os.path.join(utils.UPLOAD_FOLDER, relative_path)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error deleting file from disk: {str(e)}")
    return {"detail": f"File {file_url} deleted successfully from request {request_id}."}

@router.post("/requests/{request_id}/files")
def admin_add_files_to_request(request_id: int, files: Optional[List[UploadFile]] = File(None), admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    req = crud.get_request_by_id(db, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    file_records = req.files if req.files else []
    for file in files:
        original_filename = file.filename or "unnamed_file"
        sanitized_filename = original_filename.replace(" ", "_")
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        new_filename = f"{request_id}_{timestamp}_{sanitized_filename}"
        file_location = os.path.join(utils.UPLOAD_FOLDER, new_filename)
        file.file.seek(0)
        content = file.file.read()
        with open(file_location, "wb") as f:
            f.write(content)
        file_record = {"file_url": f"/files/{new_filename}", "file_display_name": original_filename}
        file_records.append(file_record)
    req.files = file_records
    crud.update_request(db, req)
    return {"detail": f"Files added to request {request_id}.", "files": file_records}

@router.post("/requests/{request_id}/comments")
def admin_add_comment(request_id: int, comment: str = Form(...), admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    req = crud.get_request_by_id(db, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if hasattr(req, "admin_comment") and req.admin_comment:
        req.admin_comment += f" | {comment}"
    else:
        req.admin_comment = comment
    current_time = datetime.utcnow()
    req.last_action = f"Admin comment added at {current_time.strftime('%d-%m-%Y %H:%M')}"
    req.updated_at = current_time
    crud.update_request(db, req)
    return {"detail": f"Comment added to request {request_id}.", "admin_comment": req.admin_comment}

@router.get("/all-requests", response_model=List[schemas.RequestResponse])
def admin_get_all_requests(admin: models.User = Depends(lambda token=Depends(auth.oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)), db: Session = Depends(get_db)):
    all_reqs = crud.list_all_requests(db)
    detailed_requests = []
    for r in all_reqs:
        detailed = utils.to_request_response(db, r)
        detailed["isApproved"] = "APPROVED" in r.status.upper()
        detailed_requests.append(detailed)
    return detailed_requests

@router.get("/user-files", response_model=List[dict])
def admin_user_files(admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    all_requests = crud.list_all_requests(db)
    user_files_map = {}
    for r in all_requests:
        user_id = r.initiator_id
        if not user_id:
            continue
        files = r.files if r.files else []
        if user_id not in user_files_map:
            user_obj = crud.get_user_by_id(db, user_id)
            user_name = user_obj.name if user_obj else "Unknown"
            user_files_map[user_id] = {"user_id": user_id, "user_name": user_name, "files": []}
        user_files_map[user_id]["files"].extend(files)
    result = []
    for data in user_files_map.values():
        data["file_count"] = len(data["files"])
        result.append(data)
    return result

@router.post("/requests/approve", response_model=schemas.RequestResponse)
def admin_approver_action(action: schemas.ApprovalAction, current_user: models.User = Depends(lambda token=Depends(auth.oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)), db: Session = Depends(get_db)):
    if not (2 in current_user.role or 3 in current_user.role):
        raise HTTPException(status_code=403, detail="Not authorized")
    req = crud.get_request_by_id(db, action.request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    current_time = datetime.utcnow()
    if action.approved:
        req.status = "APPROVED"
        req.last_action = f"Admin approved at {current_time.strftime('%d-%m-%Y %H:%M')}"
    else:
        req.status = "REJECTED"
        req.last_action = f"Admin rejected at {current_time.strftime('%d-%m-%Y %H:%M')}"
    req.updated_at = current_time
    crud.update_request(db, req)
    return utils.to_request_response(db, req)

@router.post("/requests/stage-approve", response_model=schemas.RequestResponse)
def admin_partial_stage_approve(action: schemas.ApprovalAction, current_user: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    req = crud.get_request_by_id(db, action.request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status in ("APPROVED", "REJECTED"):
        raise HTTPException(status_code=400, detail=f"Request is already {req.status} and cannot be changed.")
    current_time = datetime.utcnow()
    if req.status == "NEW":
        req.supervisor_approved = action.approved
        req.supervisor_comment = f"[Admin Override] {action.comment or ''}".strip()
        req.supervisor_approved_at = current_time
        req.updated_at = current_time
        if action.approved:
            if req.approvers:
                req.status = "IN_PROGRESS"
                req.last_action = f"Admin override: Supervisor stage approved at {current_time.strftime('%d-%m-%Y %H:%M')}"
                req.current_approver_index = 0
            else:
                req.status = "APPROVED"
                req.last_action = f"Admin override: Supervisor stage approved at {current_time.strftime('%d-%m-%Y %H:%M')}. No further approvers – request fully approved."
        else:
            req.status = "REJECTED"
            req.last_action = f"Admin override: Supervisor stage rejected at {current_time.strftime('%d-%m-%Y %H:%M')}"
        crud.update_request(db, req)
        return utils.to_request_response(db, req)
    if req.status == "IN_PROGRESS":
        if req.current_approver_index >= len(req.approvers):
            raise HTTPException(status_code=400, detail="No pending approver action for this request.")
        current_approver_id = req.approvers[req.current_approver_index]
        existing_action = crud.get_approver_action(db, req.id, current_approver_id)
        if existing_action:
            raise HTTPException(status_code=400, detail="Approver has already taken action on this stage.")
        new_action = {
            "request_id": req.id,
            "approver_id": current_approver_id,
            "approved": "APPROVED" if action.approved else "REJECTED",
            "received_at": current_time.strftime("%d-%m-%Y %H:%M"),
            "action_time": current_time.strftime("%d-%m-%Y %H:%M"),
            "comment": f"[Admin Override] {action.comment or ''}".strip()
        }
        crud.create_approver_action(db, new_action)
        if action.approved:
            req.current_approver_index += 1
            if req.current_approver_index >= len(req.approvers):
                req.status = "APPROVED"
                req.last_action = f"Admin override: Final stage approved at {current_time.strftime('%d-%m-%Y %H:%M')}."
            else:
                next_approver = req.approvers[req.current_approver_index]
                req.status = "IN_PROGRESS"
                req.last_action = f"Admin override: stage advanced at {current_time.strftime('%d-%m-%Y %H:%M')}. Next approver: {next_approver}"
        else:
            req.status = "REJECTED"
            req.last_action = f"Admin override: Rejected at {current_time.strftime('%d-%m-%Y %H:%M')}."
        req.updated_at = current_time
        crud.update_request(db, req)
        return utils.to_request_response(db, req)
    raise HTTPException(status_code=400, detail="Request cannot be partially approved in its current state.")

@router.get("/all-requests", response_model=List[schemas.RequestResponse])
def admin_all_requests(current_user: models.User = Depends(lambda token=Depends(auth.oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)), db: Session = Depends(get_db)):
    if not (2 in current_user.role or 3 in current_user.role):
        raise HTTPException(status_code=403, detail="Not authorized")
    all_requests = crud.list_all_requests(db)
    responses = [utils.to_request_response(db, r) for r in all_requests]
    return responses

@router.get("/admin/total-requests")
def admin_total_requests(current_user: models.User = Depends(lambda token=Depends(auth.oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)), db: Session = Depends(get_db)):
    if not (2 in current_user.role or 3 in current_user.role):
        raise HTTPException(status_code=403, detail="Not authorized")
    total = len(crud.list_all_requests(db))
    return {"total_requests": total}

@router.get("/admin/pending-requests")
def admin_pending_requests(current_user: models.User = Depends(lambda token=Depends(auth.oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)), db: Session = Depends(get_db)):
    if not (2 in current_user.role or 3 in current_user.role):
        raise HTTPException(status_code=403, detail="Not authorized")
    pending = [r for r in crud.list_all_requests(db) if r.status in ("NEW", "IN_PROGRESS")]
    return {"total_pending_requests": len(pending)}

@router.delete("/sessions/clear-all")
def admin_clear_all_sessions(admin: models.User = Depends(get_admin_user), db: Session = Depends(get_db)):
    db.query(models.Token).delete()
    db.commit()
    return {"detail": "Cleared all sessions for all active users."}
