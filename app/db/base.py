# Import all the models, so that Base has them before being
# imported by Alembic
from app.db.base_class import Base
from app.models.user import User
from app.models.session import UserSession
from app.models.chat import ChatHistory
from app.models.feedback_models import UserFeedback, PromptVersion, GoldenExample
from app.models.schema_models import SchemaMetadata, SchemaSemanticMapping, SchemaBusinessRule

# Add any other models here
