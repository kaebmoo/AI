from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.services.auth_service import AuthService
from app.schemas.user_schemas import UserCreate, UserUpdate, UserResponse, ListUserResponse

router = APIRouter()

@router.get("", response_model=ListUserResponse)
def list_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
):
    """
    List all users. Admin only.
    """
    total = db.query(User).count()
    users = db.query(User).offset(skip).limit(limit).all()
    return {"users": users, "total": total}

@router.post("", response_model=UserResponse)
def create_user(
    user_in: UserCreate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
):
    """
    Create a new user. Admin only.
    """
    auth_service = AuthService(db)
    
    # Check if user exists
    existing = db.query(User).filter(User.email == user_in.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    if user_in.password:
        # Create with password
        user = auth_service.create_admin_user(
            email=user_in.email, 
            password=user_in.password, 
            display_name=user_in.display_name
        )
        # Update other fields that might not be set by create_admin_user
        if user_in.role:
            user.role = user_in.role
        if user_in.department:
            user.department = user_in.department
        if user_in.is_active is not None:
            user.is_active = user_in.is_active
        db.commit()
        db.refresh(user)
    else:
        # Create OTP user
        user = User(
            email=user_in.email,
            display_name=user_in.display_name,
            role=user_in.role,
            department=user_in.department,
            is_active=user_in.is_active
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
    return user

@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_in: UserUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
):
    """
    Update user. Admin only.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    auth_service = AuthService(db)
    
    # Update password if provided
    if user_in.password:
        hashed = auth_service.get_password_hash(user_in.password)
        user.hashed_password = hashed
        user.force_password_change = True
        
    # Update other fields
    if user_in.display_name is not None:
        user.display_name = user_in.display_name
    if user_in.role is not None:
        user.role = user_in.role
    if user_in.department is not None:
        user.department = user_in.department
    if user_in.is_active is not None:
        user.is_active = user_in.is_active
        
    db.commit()
    db.refresh(user)
    return user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
):
    """
    Delete user. Admin only.
    """
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    db.delete(user)
    db.commit()
    return None
