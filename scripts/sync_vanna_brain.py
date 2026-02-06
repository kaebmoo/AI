
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.vanna_service import VannaService
from app.services.schema_service import SchemaService
from app.config import settings

def main():
    print("🚀 Initializing Vanna Brain Sync...")

    # Initialize Services with config from .env
    vanna = VannaService(config={
        "path": settings.VANNA_CHROMA_PATH,
        "distance_threshold": settings.VANNA_DISTANCE_THRESHOLD
    })
    schema_service = SchemaService() # Defaults to env DB path
    
    # Run Sync
    vanna.sync_brain(schema_service)
    
    print("\n✅ Sync Complete! storage at ./chroma_db")
    print("You can now use VannaService to retrieve context.")

if __name__ == "__main__":
    main()
