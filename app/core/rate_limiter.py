from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request

# Initialize limiter with remote address key
# In production, this should probably use Redis
limiter = Limiter(key_func=get_remote_address)

def rate_limit_custom_key(request: Request):
    """Custom key function for rate limiting (e.g. by user ID if authenticated)"""
    # Try to get user ID from state if available (set by auth middleware)
    if hasattr(request.state, "user") and request.state.user:
        return str(request.state.user.id)
    return get_remote_address(request)
