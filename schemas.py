from typing import List, Optional
from pydantic import BaseModel

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: Optional[int] = None

class UserBase(BaseModel):
    name: str
    role: List[int] = [0]
    email: str

class UserCreate(UserBase):
    username: str
    password: str

class UserResponse(UserBase):
    id: int
    username: str

    class Config:
        orm_mode = True

class ApproverActionResponse(BaseModel):
    approver_id: int
    approved: Optional[str] = None
    action_time: Optional[str] = None
    received_at: Optional[str] = None
    comment: Optional[str] = None

    class Config:
        orm_mode = True

class RequestResponse(BaseModel):
    id: int
    initiator_id: int
    supervisor_id: int
    subject: str
    description: str
    area: str
    project: str
    tower: str
    department: str
    references: Optional[str] = None
    priority: str
    approvers: List[int]
    current_approver_index: int
    status: str
    created_at: str
    updated_at: str
    last_action: Optional[str] = None
    supervisor_approved_at: Optional[str] = None
    initiator_name: Optional[str] = None
    supervisor_name: Optional[str] = None
    pending_at: Optional[str] = None
    approver_actions: Optional[List[ApproverActionResponse]] = None
    files: Optional[List[dict]] = []

    class Config:
        orm_mode = True

class ApprovalAction(BaseModel):
    request_id: int
    approved: bool
    comment: Optional[str] = None

class SessionInfo(BaseModel):
    session_id: str
    login_time: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

# Additional schemas for admin user operations
class AdminEditUser(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    name: Optional[str] = None
    role: Optional[List[int]] = None
    email: Optional[str] = None

class AdminCreateUser(BaseModel):
    username: str
    password: str
    name: str
    role: List[int]
    email: str
