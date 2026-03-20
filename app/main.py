from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.core.logging import setup_logging
from app.core.middleware import RequestIDMiddleware
from app.core.rate_limiter import limiter, RateLimitExceeded, _rate_limit_exceeded_handler
from app.services.mcp_client import MCPClientService

# Setup logging
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connect to MCP Servers
    mcp_client = MCPClientService()
    async with mcp_client.connected():
        app.state.mcp_client = mcp_client
        yield
        
    # Shutdown handled by context manager exit

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan
)

# Initialize Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Set all CORS enabled origins
# Configure CORS_ORIGINS in .env as comma-separated list of allowed origins
cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestIDMiddleware)

@app.get("/")
def root():
    return {"message": "Welcome to NT AI Assistant API", "version": "1.0.0"}

# Note: Routers will be included here as they are implemented
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.admin import router as admin_router
from app.api.v1.users import router as users_router
from app.api.v1.schema_analyzer import router as analyzer_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.admin_agent import router as admin_agent_router
from app.api.v1.query import router as query_router

app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(chat_router, prefix=f"{settings.API_V1_STR}/chat", tags=["chat"])
app.include_router(feedback_router, prefix=f"{settings.API_V1_STR}/feedback", tags=["feedback"])
app.include_router(admin_router, prefix=f"{settings.API_V1_STR}/admin", tags=["admin"])
app.include_router(users_router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(analyzer_router, prefix=f"{settings.API_V1_STR}/admin/analyzer", tags=["analyzer"])
app.include_router(conversations_router, prefix=f"{settings.API_V1_STR}/conversations", tags=["conversations"])
app.include_router(admin_agent_router, prefix=f"{settings.API_V1_STR}/admin", tags=["admin-agent"])
app.include_router(query_router, prefix=f"{settings.API_V1_STR}/query", tags=["query"])
