from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    display_name: str
    role: str = "user"
    department: Optional[str] = None
    is_active: bool = True

class UserCreate(UserBase):
    password: Optional[str] = None # Optional for OTP users, required for admin if enforced logic

class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None # For password reset

class UserResponse(UserBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ListUserResponse(BaseModel):
    users: list[UserResponse]
    total: int
