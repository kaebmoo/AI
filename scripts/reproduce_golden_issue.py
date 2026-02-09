import sys
import os
# Add project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
import app.db.base  # Register all models
from app.models.feedback_models import GoldenExample
from app.schemas.admin_schemas import GoldenExampleResponse

def test():
    print("Connecting to DB...")
    db = SessionLocal()
    try:
        examples = db.query(GoldenExample).all()
        print(f"Found {len(examples)} examples.")
        for e in examples:
            print(f"Processing Example ID: {e.id}")
            print(f"  - Pattern: {e.question_pattern[:50]}...")
            print(f"  - SQL: {e.expected_sql[:50]}...")
            print(f"  - AddedBy: {e.added_by} (Type: {type(e.added_by)})")
            print(f"  - CreatedAt: {e.created_at} (Type: {type(e.created_at)})")
            
            # Try validation
            try:
                model = GoldenExampleResponse.model_validate(e)
                print(f"  - Serialization Success: {model.model_dump_json()}")
            except Exception as ex:
                print(f"  - Serialization FAILED for ID {e.id}: {ex}")
                import traceback
                traceback.print_exc()
    except Exception as e:
        print(f"DB Query Failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test()
