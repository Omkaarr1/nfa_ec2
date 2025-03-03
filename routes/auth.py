from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import List
import schemas, crud, auth, models
from database import get_db
from datetime import datetime

router = APIRouter()
oauth2_scheme = auth.oauth2_scheme  # re‐use our oauth2_scheme from auth.py

@router.post("/register", response_model=schemas.UserResponse)
def register_user(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    if crud.get_user_by_username(db, user_data.username):
        raise HTTPException(status_code=400, detail="User with this username already exists.")
    hashed_password = auth.get_password_hash(user_data.password)
    new_user = crud.create_user(db, user_data, hashed_password)
    return new_user

@router.post("/login", response_model=schemas.Token)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = crud.get_user_by_username(db, form_data.username)
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    access_token = auth.create_access_token(data={"sub": str(user.id)})
    client_ip = request.client.host if request.client else "Unknown"
    user_agent = request.headers.get("User-Agent", "Unknown")
    token_details = {
        "user_id": user.id,
        "created_at": datetime.utcnow().isoformat(),
        "ip_address": client_ip,
        "user_agent": user_agent
    }
    crud.create_token(db, access_token, token_details)
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
def logout(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    crud.remove_token(db, token)
    return {"detail": "Successfully logged out."}

@router.post("/logout_all")
def logout_all(current_user: models.User = Depends(lambda token=Depends(oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)), db: Session = Depends(get_db)):
    crud.remove_tokens_by_user(db, current_user.id)
    return {"detail": "Logged out from all sessions."}

@router.get("/sessions", response_model=List[schemas.SessionInfo])
def list_sessions(current_user: models.User = Depends(lambda token=Depends(oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)), db: Session = Depends(get_db)):
    tokens = crud.list_tokens_by_user(db, current_user.id)
    result = []
    for t in tokens:
        result.append({
            "session_id": t.token,
            "login_time": t.created_at,
            "ip_address": t.ip_address,
            "user_agent": t.user_agent
        })
    return result

@router.get("/users/me", response_model=schemas.UserResponse)
def get_current_user_info(current_user: models.User = Depends(lambda token=Depends(oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db))):
    return current_user

@router.get("/users/{user_id}", response_model=schemas.UserResponse)
def read_user(user_id: int, current_user: models.User = Depends(lambda token=Depends(oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)), db: Session = Depends(get_db)):
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.get("/users/", response_model=List[schemas.UserResponse])
def list_users(current_user: models.User = Depends(lambda token=Depends(oauth2_scheme), db=Depends(get_db): auth.get_current_user(token, db)), db: Session = Depends(get_db)):
    return crud.list_all_users(db)
