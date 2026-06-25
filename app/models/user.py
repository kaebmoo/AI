from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base_class import Base

class User(Base):
    """
    User model represents a registered user in the system.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String)
    department = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    role = Column(String, default="user") # user, admin, viewer
    # Stub for future BU-level read access (Plan 6 / multi-tenant). NULL = no
    # restriction. NOT enforced today — all authenticated users see all business
    # data. To activate: filter queries (and scope the result cache) by this value
    # in the query pipeline. Kept intentionally — do not delete as "unused".
    allowed_bu_access = Column(String, nullable=True)
    
    # Password based auth
    hashed_password = Column(String, nullable=True)
    force_password_change = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sessions = relationship("UserSession", back_populates="user")
    chats = relationship("ChatHistory", back_populates="user")
    conversations = relationship("Conversation", back_populates="user")
