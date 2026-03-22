import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import engine, config_engine
from app.db.base_class import Base, ConfigBase
# Import all models to ensure they are registered
from app.models.user import User
from app.models.session import UserSession
from app.models.otp import OTPRequest
from app.models.chat import ChatHistory
from app.models.feedback_models import GoldenExample, UserFeedback
# Config models (registered on ConfigBase)
from app.models.schema_models import SchemaMetadata, SchemaSemanticMapping, SchemaBusinessRule

def init_db():
    print("Creating app tables in app.db...")
    Base.metadata.create_all(bind=engine)
    print("Creating config tables in config.db...")
    ConfigBase.metadata.create_all(bind=config_engine)
    print("Tables created successfully.")

if __name__ == "__main__":
    init_db()
