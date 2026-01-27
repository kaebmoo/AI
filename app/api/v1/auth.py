from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from sqlalchemy.orm import Session

from app.api import deps
from app.schemas.auth import LoginRequest, VerifyOTPRequest, TokenResponse
from app.services.otp_service import OTPService
from app.services.email_service import EmailService
from app.services.auth_service import AuthService
from app.core.exceptions import AppError

router = APIRouter()

@router.post("/login", status_code=200)
async def login(
    login_data: LoginRequest,
    request: Request,
    db: Session = Depends(deps.get_db)
):
    """
    Initiate login process by requesting OTP.
    """
    email_service = EmailService()
    otp_service = OTPService(db, email_service)
    
    try:
        ip_address = request.client.host if request.client else "unknown"
        success, message = await otp_service.request_otp(
            email=login_data.email,
            platform=login_data.platform,
            ip_address=ip_address
        )
        return {"message": message}
    except AppError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/verify", response_model=TokenResponse)
def verify_otp(
    verify_data: VerifyOTPRequest,
    request: Request,
    db: Session = Depends(deps.get_db)
):
    """
    Verify OTP and return session token.
    """
    email_service = EmailService() # Needed for OTPService init
    otp_service = OTPService(db, email_service)
    auth_service = AuthService(db)
    
    try:
        # Verify OTP
        success, message = otp_service.verify_otp(
            email=verify_data.email,
            otp=verify_data.otp,
            platform=verify_data.platform
        )
        
        if not success:
             raise HTTPException(status_code=400, detail=message)
             
        # Create User if not exists
        user = auth_service.get_or_create_user(verify_data.email)
        
        # Create Session
        ip_address = request.client.host if request.client else "unknown"
        session = auth_service.create_session(
            user=user,
            platform=verify_data.platform,
            ip_address=ip_address,
            user_agent=request.headers.get("user-agent")
        )
        
        return {
            "access_token": session.session_token,
            "token_type": "bearer",
            "user_email": user.email,
            "display_name": user.display_name
        }
        
    except AppError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/logout")
def logout(
    token: str = Depends(deps.header_scheme),
    db: Session = Depends(deps.get_db)
):
    """
    Logout current user.
    """
    if token:
        auth_service = AuthService(db)
        auth_service.logout(token)
    return {"message": "Successfully logged out"}
