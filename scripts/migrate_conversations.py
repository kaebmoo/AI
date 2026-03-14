"""
Migration script: Create conversations table and migrate existing data.

This script:
1. Creates the 'conversations' table if it doesn't exist
2. Migrates existing chat_history records that have conversation_id
   into the new conversations table
3. Safe to run multiple times (idempotent)

Usage:
    python scripts/migrate_conversations.py
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect
from app.db.session import engine, SessionLocal
from app.db.base import Base  # Ensures all models are imported
from app.models.conversation import Conversation
from app.models.chat import ChatHistory


def migrate():
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    # Step 1: Create conversations table if not exists
    if "conversations" not in existing_tables:
        print("Creating 'conversations' table...")
        Conversation.__table__.create(bind=engine)
        print("Table created.")
    else:
        print("Table 'conversations' already exists, skipping creation.")

    # Step 2: Migrate existing chat_history data
    db = SessionLocal()
    try:
        # Find distinct conversation_ids in chat_history that don't yet have
        # a conversations record
        result = db.execute(text("""
            SELECT DISTINCT ch.conversation_id
            FROM chat_history ch
            WHERE ch.conversation_id IS NOT NULL
              AND ch.conversation_id != ''
              AND NOT EXISTS (
                  SELECT 1 FROM conversations c WHERE c.id = ch.conversation_id
              )
        """))
        orphan_conv_ids = [row[0] for row in result]

        if not orphan_conv_ids:
            print("No orphaned conversation_ids to migrate.")
        else:
            print(f"Found {len(orphan_conv_ids)} conversation(s) to migrate...")

        migrated = 0
        for conv_id in orphan_conv_ids:
            # Get first and last chat entry for this conversation
            first_chat = db.query(ChatHistory).filter(
                ChatHistory.conversation_id == conv_id
            ).order_by(ChatHistory.created_at.asc()).first()

            last_chat = db.query(ChatHistory).filter(
                ChatHistory.conversation_id == conv_id
            ).order_by(ChatHistory.created_at.desc()).first()

            msg_count = db.query(ChatHistory).filter(
                ChatHistory.conversation_id == conv_id
            ).count()

            if not first_chat:
                continue

            # Generate title from first question (max 60 chars)
            title = None
            if first_chat.question:
                title = first_chat.question[:60]
                if len(first_chat.question) > 60:
                    title += "..."

            conv = Conversation(
                id=conv_id,
                user_id=first_chat.user_id,
                title=title,
                created_at=first_chat.created_at,
                updated_at=last_chat.created_at if last_chat else first_chat.created_at,
                message_count=msg_count,
                is_archived=False,
            )
            db.add(conv)
            migrated += 1

            # Commit in batches
            if migrated % 100 == 0:
                db.commit()
                print(f"  Migrated {migrated}...")

        db.commit()
        print(f"Migration complete. Migrated {migrated} conversation(s).")

    except Exception as e:
        db.rollback()
        print(f"Error during migration: {e}")
        raise
    finally:
        db.close()

    # Step 3: Note about FK constraint
    # SQLite doesn't support ALTER TABLE ADD FOREIGN KEY.
    # The FK is defined in the model (ChatHistory.conversation_id -> conversations.id)
    # and will be enforced by SQLAlchemy on new records.
    # For existing records without a conversations row, conversation_id remains as-is.
    print("\nNote: FK constraint is defined in the model. Existing chat_history records")
    print("without a matching conversations row will still work (nullable FK).")


if __name__ == "__main__":
    migrate()
