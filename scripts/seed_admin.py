from app.db.session import SessionLocal
from app.services.auth_service import AuthService
from app.db import base # Import all models
from app.services.auth_service import AuthService

def seed_admin():
    db = SessionLocal()
    try:
        auth_service = AuthService(db)
        admin_email = "admin@ntplc.co.th"
        admin_pass = "admin"
        
        user = auth_service.create_admin_user(admin_email, admin_pass, "System Admin")
        print(f"Admin user created/updated: {user.email}")
        
    finally:
        db.close()

if __name__ == "__main__":
    seed_admin()
