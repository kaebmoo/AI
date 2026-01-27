import sys
import os
import inspect # For introspection
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from app.main import app
from app.core.rate_limiter import limiter
from app.celery import celery_app
from app.services.cache_service import CacheService

def check_feature(name, condition, details=""):
    status = "✅ PASS" if condition else "❌ FAIL"
    print(f"{status} - {name}")
    if not condition and details:
        print(f"   Details: {details}")

def verify_phases():
    print("=== Verifying Phase 1-3 Completion ===\n")

    # 1. Rate Limiter
    has_limiter = hasattr(app.state, "limiter")
    check_feature("Rate Limiter Middleware attached to App", has_limiter)
    
    # Check if limiter is actually slowapi Limiter
    is_slowapi = "slowapi" in str(type(app.state.limiter))
    check_feature("Rate Limiter is slowapi instance", is_slowapi)

    # 2. Feedback API
    routes = [route.path for route in app.routes]
    feedback_endpoints = [r for r in routes if "/feedback" in r]
    check_feature("Feedback API endpoints registered", len(feedback_endpoints) > 0, f"Found: {feedback_endpoints}")
    
    has_submit = any("/feedback/{chat_id}" in r for r in feedback_endpoints)
    check_feature("Feedback Submit Endpoint", has_submit)
    
    has_pending = any("/feedback/pending" in r for r in feedback_endpoints)
    check_feature("Feedback Pending Review Endpoint", has_pending)

    # 3. Celery
    check_feature("Celery App initialized", celery_app is not None)
    check_feature("Celery Broker Configured", celery_app.conf.broker_url is not None)

    # 4. Cache Service
    try:
        cache = CacheService(redis_url="redis://mock:6379/0")
        check_feature("Cache Service Instantiation", cache is not None)
        # We won't test connection as Redis might not be running in this script env
    except Exception as e:
        check_feature("Cache Service Instantiation", False, str(e))

    # 5. Docker files
    docker_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docker")
    dockerfile = os.path.exists(os.path.join(docker_dir, "Dockerfile"))
    compose = os.path.exists(os.path.join(docker_dir, "docker-compose.yml"))
    
    check_feature("Dockerfile exists", dockerfile)
    check_feature("docker-compose.yml exists", compose)

if __name__ == "__main__":
    verify_phases()
