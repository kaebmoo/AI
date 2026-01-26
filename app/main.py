from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.logging import setup_logging
from app.core.middleware import RequestIDMiddleware

# Setup logging
setup_logging()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
)

# Set all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestIDMiddleware)

@app.get("/")
def root():
    return {"message": "Welcome to NT Revenue Assistant API", "version": "1.0.0"}

# Note: Routers will be included here as they are implemented
from app.api.v1.auth import router as auth_router

app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])

