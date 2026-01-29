from pydantic import BaseModel, EmailStr
from typing import Optional

class LoginRequest(BaseModel):
    email: EmailStr
    password: Optional[str] = None
    platform: str = "web"

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str
    platform: str = "web"

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_email: str
    display_name: str
