from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    role = Column(ARRAY(Integer), default=[0])
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    requests_initiated = relationship("Request", back_populates="initiator", foreign_keys='Request.initiator_id')
    requests_supervised = relationship("Request", back_populates="supervisor", foreign_keys='Request.supervisor_id')
    tokens = relationship("Token", back_populates="user")

class Request(Base):
    __tablename__ = "requests"
    id = Column(Integer, primary_key=True, index=True)
    initiator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    supervisor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subject = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    area = Column(String, nullable=False)
    project = Column(String, nullable=False)
    tower = Column(String, nullable=False)
    department = Column(String, nullable=False)
    references = Column(String, nullable=True)
    priority = Column(String, nullable=False)
    approvers = Column(ARRAY(Integer), default=[])
    current_approver_index = Column(Integer, default=0)
    status = Column(String, default="NEW")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_action = Column(String, nullable=True)
    supervisor_approved_at = Column(DateTime, nullable=True)
    supervisor_approved = Column(Boolean, nullable=True)
    supervisor_comment = Column(Text, nullable=True)
    files = Column(JSONB, default=[])

    initiator = relationship("User", foreign_keys=[initiator_id], back_populates="requests_initiated")
    supervisor = relationship("User", foreign_keys=[supervisor_id], back_populates="requests_supervised")
    approver_actions = relationship("ApproverAction", back_populates="request")

class ApproverAction(Base):
    __tablename__ = "approver_actions"
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=False)
    approver_id = Column(Integer, nullable=False)
    approved = Column(String, nullable=False)  # "APPROVED" or "REJECTED"
    received_at = Column(String, nullable=True)
    action_time = Column(String, nullable=True)
    comment = Column(Text, nullable=True)
    approved_by = Column(String, nullable=True)

    request = relationship("Request", back_populates="approver_actions")

class ErrorLog(Base):
    __tablename__ = "error_logs"
    id = Column(Integer, primary_key=True, index=True)
    endpoint = Column(String, nullable=False)
    error_message = Column(Text, nullable=False)
    traceback = Column(Text, nullable=False)
    created_at = Column(String, nullable=False)

class Token(Base):
    __tablename__ = "tokens"
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(String, nullable=False)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    user = relationship("User", back_populates="tokens")
