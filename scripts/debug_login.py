from app.db.session import SessionLocal
from app.services.auth_service import AuthService
from app.db import base # Registers all models including ChatHistory
from app.models.user import User
import bcrypt

def debug_login():
    db = SessionLocal()
    try:
        print("--- Debugging Login ---")
        email = "admin@ntplc.co.th"
        password = "admin"
        
        # 1. Check User in DB
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"❌ User {email} NOT FOUND in database.")
            return

        print(f"✅ User found: {user.email}, Role: {user.role}")
        print(f"   Hashed Password in DB: {user.hashed_password}")
        
        if not user.hashed_password:
             print("❌ User has NO password set.")
             return

        # 2. Test bcrypt directly
        print("\n--- Testing bcrypt match ---")
        try:
            # Standard bcrypt uses bytes
            match = bcrypt.checkpw(password.encode('utf-8'), user.hashed_password.encode('utf-8'))
            print(f"   bcrypt.checkpw(bytes) -> {match}")
        except Exception as e:
             print(f"   bcrypt bytes check failed: {e}")

        # 3. Test AuthService
        print("\n--- Testing AuthService.authenticate_user ---")
        auth_service = AuthService(db)
        auth_user = auth_service.authenticate_user(email, password)
        if auth_user:
            print("✅ AuthService.authenticate_user SUCCEEDED")
        else:
            print("❌ AuthService.authenticate_user FAILED")

    finally:
        db.close()

if __name__ == "__main__":
    debug_login()
