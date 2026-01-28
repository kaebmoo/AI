import sys
import os

# Add app to path
sys.path.append(os.getcwd())

from app.services.schema_service import SchemaService

def verify_rules():
    print("Verifying Dynamic SQL Rules...\n")
    
    # Test SQLite (Default)
    sqlite_svc = SchemaService(db_engine="sqlite")
    sqlite_prompt = sqlite_svc._get_syntax_rules("thai")
    print(f"[SQLite Rules]:\n{sqlite_prompt}\n")
    if "||" not in sqlite_prompt or "strftime" not in sqlite_prompt:
        print("❌ SQLite verification FAILED")
    else:
        print("✅ SQLite verification PASSED")

    # Test MSSQL
    mssql_svc = SchemaService(db_engine="mssql")
    mssql_prompt = mssql_svc._get_syntax_rules("thai")
    print(f"\n[MSSQL Rules]:\n{mssql_prompt}\n")
    if "+" not in mssql_prompt or "FORMAT" not in mssql_prompt or "TOP" not in mssql_prompt:
        print("❌ MSSQL verification FAILED")
    else:
        print("✅ MSSQL verification PASSED")

    # Test Postgres
    pg_svc = SchemaService(db_engine="postgresql")
    pg_prompt = pg_svc._get_syntax_rules("thai")
    print(f"\n[PostgreSQL Rules]:\n{pg_prompt}\n")
    if "CONCAT" not in pg_prompt or "to_char" not in pg_prompt:
        print("❌ PostgreSQL verification FAILED")
    else:
        print("✅ PostgreSQL verification PASSED")

if __name__ == "__main__":
    verify_rules()
