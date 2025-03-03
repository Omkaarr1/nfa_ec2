import os
import io
import textwrap
from datetime import datetime
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import crud, models
from sqlalchemy.orm import Session
from config import IST_OFFSET

UPLOAD_FOLDER = "nfa_files"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def normalize_url(url: str) -> str:
    return url.strip().lstrip("/").lower()

def to_request_response(db: Session, req: models.Request):
    initiator = crud.get_user_by_id(db, req.initiator_id)
    supervisor = crud.get_user_by_id(db, req.supervisor_id)
    initiator_name = initiator.name if initiator else "NA"
    supervisor_name = supervisor.name if supervisor else "NA"

    # Build approval_hierarchy: Supervisor followed by each approver entry.
    approval_hierarchy = []
    approval_hierarchy.append({
        "role": "Supervisor",
        "user_id": req.supervisor_id,
        "name": supervisor_name,
        "approved": "Approved" if req.supervisor_approved is True else ("REJECTED" if req.supervisor_approved is False else "Pending"),
        "received_at": req.created_at.strftime("%d-%m-%Y %H:%M") if req.created_at else "NA",
        "action_time": req.supervisor_approved_at.strftime("%d-%m-%Y %H:%M") if req.supervisor_approved_at else "NA",
        "comment": req.supervisor_comment or "NA"
    })
    approver_actions = crud.list_approver_actions_by_request(db, req.id)
    approvers_list = req.approvers if req.approvers else []
    for approver_id in approvers_list:
        action_obj = next((a for a in approver_actions if a.approver_id == approver_id), None)
        if action_obj:
            approval_hierarchy.append({
                "role": "Approver",
                "user_id": approver_id,
                "name": crud.get_user_by_id(db, approver_id).name if crud.get_user_by_id(db, approver_id) else "NA",
                "approved": action_obj.approved or "NA",
                "received_at": action_obj.received_at or "NA",
                "action_time": action_obj.action_time or "NA",
                "comment": action_obj.comment or "NA"
            })
        else:
            approval_hierarchy.append({
                "role": "Approver",
                "user_id": approver_id,
                "name": crud.get_user_by_id(db, approver_id).name if crud.get_user_by_id(db, approver_id) else "NA",
                "approved": "Pending",
                "received_at": "NA",
                "action_time": "NA",
                "comment": "NA"
            })

    pending_at = "NA"
    if req.status == "IN_PROGRESS" and req.current_approver_index < len(approvers_list):
        next_approver = crud.get_user_by_id(db, approvers_list[req.current_approver_index])
        pending_at = f"Approver: {next_approver.name}" if next_approver else "Approver: NA"
    elif req.status == "NEW":
        pending_at = "Supervisor"

    response = {
        "id": req.id,
        "initiator_id": req.initiator_id,
        "supervisor_id": req.supervisor_id,
        "subject": req.subject or "NA",
        "description": req.description or "NA",
        "area": req.area or "NA",
        "project": req.project or "NA",
        "tower": req.tower or "NA",
        "department": req.department or "NA",
        "references": req.references or "NA",
        "priority": req.priority or "NA",
        "approvers": approvers_list,
        "current_approver_index": req.current_approver_index,
        "status": req.status or "NA",
        "created_at": req.created_at.strftime("%d-%m-%Y %H:%M") if req.created_at else "NA",
        "updated_at": req.updated_at.strftime("%d-%m-%Y %H:%M") if req.updated_at else "NA",
        "last_action": req.last_action or "NA",
        "supervisor_approved_at": req.supervisor_approved_at.strftime("%d-%m-%Y %H:%M") if req.supervisor_approved_at else "NA",
        "initiator_name": initiator_name,
        "supervisor_name": supervisor_name,
        "pending_at": pending_at,
        "approver_actions": [a.__dict__ for a in approver_actions],
        "approval_hierarchy": approval_hierarchy,
        "files": req.files or []
    }
    return response

def generate_pdf(db: Session, req: models.Request):
    initiator = crud.get_user_by_id(db, req.initiator_id)
    initiator_name = initiator.name if initiator else "NA"
    supervisor = crud.get_user_by_id(db, req.supervisor_id)
    supervisor_name = supervisor.name if supervisor else "NA"

    def valOrNA(val):
        return val if val and str(val).strip() != "" else "NA"

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left_margin = 40
    right_margin = 40
    current_y = height - 60
    line_height = 14

    # Draw header
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, current_y, "Jaypee Infratech Limited")
    current_y -= 25
    c.setLineWidth(1)
    c.line(left_margin, current_y, width - right_margin, current_y)
    current_y -= 20
    c.setFont("Helvetica-Bold", 12)
    c.drawString(left_margin, current_y, f"NFA No. {valOrNA(req.id)}")
    current_y -= line_height + 5
    c.drawString(left_margin, current_y, f"Initiator: {initiator_name}")
    current_y -= line_height + 5
    c.drawString(left_margin, current_y, f"Recommendor: {supervisor_name}")
    current_y -= line_height + 5
    c.drawString(left_margin, current_y, f"Subject: {valOrNA(req.subject)}")
    current_y -= line_height + 5
    c.drawString(left_margin, current_y, "Description:")
    current_y -= line_height
    c.setFont("Helvetica", 12)
    description_text = valOrNA(req.description)
    wrapped_desc = textwrap.wrap(description_text, width=90)
    for line in wrapped_desc:
        c.drawString(left_margin, current_y, line)
        current_y -= line_height
    current_y -= 5

    # Additional details (area, project, tower, etc.)
    c.setFont("Helvetica-Bold", 12)
    area_text = f"Area: {valOrNA(req.area)}"
    project_text = f"Project: {valOrNA(req.project)}"
    c.drawString(left_margin, current_y, area_text)
    c.drawString(width / 2, current_y, project_text)
    current_y -= line_height + 5

    tower_text = f"Tower: {valOrNA(req.tower)}"
    dept_text = f"Department: {valOrNA(req.department)}"
    c.drawString(left_margin, current_y, tower_text)
    c.drawString(width / 2, current_y, dept_text)
    current_y -= line_height + 5

    ref_text = f"Reference: {valOrNA(req.references)}"
    priority_text = f"Priority: {valOrNA(req.priority)}"
    c.drawString(left_margin, current_y, ref_text)
    c.drawString(width / 2, current_y, priority_text)
    current_y -= line_height + 15

    c.setLineWidth(1)
    c.line(left_margin, current_y, width - right_margin, current_y)
    current_y -= 20
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, current_y, "NFA Approval Summary")
    current_y -= 25
    c.setLineWidth(1)
    c.line(left_margin, current_y, width - right_margin, current_y)
    current_y -= 20

    c.setFont("Helvetica", 10)
    c.drawString(left_margin, current_y, "Approval Summary:")
    current_y -= line_height

    c.setFont("Helvetica-Oblique", 12)
    footer_text = "This is a system generated Approved NFA, does not require signature."
    c.drawCentredString(width / 2, 30, footer_text)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer
