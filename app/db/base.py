# Import all the models, so that Base has them before being
# imported by Alembic
from app.db.base_class import Base
from app.models.user import User
from app.models.session import UserSession
from app.models.chat import ChatHistory
from app.models.feedback_models import UserFeedback, GoldenExample
from app.models.schema_models import SchemaMetadata, SchemaSemanticMapping, SchemaBusinessRule
from app.models.chat_session import ChatSessionData
from app.models.conversation import Conversation

# Add any other models here
