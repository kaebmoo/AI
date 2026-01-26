import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from app.core.logging import request_id_var

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add request_id to all requests for log correlation"""
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Get or generate request_id
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        
        # Set in context for logging
        token = request_id_var.set(request_id)
        
        # Add to request state for handlers
        request.state.request_id = request_id
        
        try:
            # Process request
            response = await call_next(request)
            
            # Add to response headers
            response.headers["X-Request-ID"] = request_id
            
            return response
        finally:
            # Reset context var
            request_id_var.reset(token)
