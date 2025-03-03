from sqlalchemy.orm import Session
import models, schemas
from datetime import datetime

def create_user(db: Session, user: schemas.UserCreate, hashed_password: str):
    db_user = models.User(
        username=user.username,
        name=user.name,
        role=user.role,
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def get_user_by_id(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def list_all_users(db: Session):
    return db.query(models.User).all()

def update_user(db: Session, user: models.User):
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def create_request(db: Session, request_data: dict):
    db_request = models.Request(**request_data)
    db.add(db_request)
    db.commit()
    db.refresh(db_request)
    return db_request

def get_request_by_id(db: Session, request_id: int):
    return db.query(models.Request).filter(models.Request.id == request_id).first()

def update_request(db: Session, request_obj: models.Request):
    db.add(request_obj)
    db.commit()
    db.refresh(request_obj)
    return request_obj

def list_all_requests(db: Session):
    return db.query(models.Request).all()

def create_approver_action(db: Session, action_data: dict):
    db_action = models.ApproverAction(**action_data)
    db.add(db_action)
    db.commit()
    db.refresh(db_action)
    return db_action

def get_approver_action(db: Session, request_id: int, approver_id: int):
    return db.query(models.ApproverAction).filter(
        models.ApproverAction.request_id == request_id,
        models.ApproverAction.approver_id == approver_id
    ).first()

def list_approver_actions_by_request(db: Session, request_id: int):
    return db.query(models.ApproverAction).filter(models.ApproverAction.request_id == request_id).all()

def delete_approver_actions_by_request(db: Session, request_id: int):
    db.query(models.ApproverAction).filter(models.ApproverAction.request_id == request_id).delete()
    db.commit()

def create_error_log(db: Session, log_data: dict):
    db_log = models.ErrorLog(**log_data)
    db.add(db_log)
    db.commit()

def create_token(db: Session, token: str, details: dict):
    db_token = models.Token(
        token=token,
        user_id=details.get("user_id"),
        created_at=details.get("created_at"),
        ip_address=details.get("ip_address"),
        user_agent=details.get("user_agent")
    )
    db.add(db_token)
    db.commit()
    db.refresh(db_token)
    return db_token

def get_token_details(db: Session, token: str):
    return db.query(models.Token).filter(models.Token.token == token).first()

def list_tokens_by_user(db: Session, user_id: int):
    return db.query(models.Token).filter(models.Token.user_id == user_id).all()

def remove_token(db: Session, token: str):
    db.query(models.Token).filter(models.Token.token == token).delete()
    db.commit()

def remove_tokens_by_user(db: Session, user_id: int):
    db.query(models.Token).filter(models.Token.user_id == user_id).delete()
    db.commit()
