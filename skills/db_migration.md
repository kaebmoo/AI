---
name: Database Migration
description: How to manage database migrations using Alembic
---

# Database Migration Skill

This skill describes how to handle database schema changes.

## Prerequisites
- `alembic` installed
- `alembic.ini` configured

## Steps

1. **Initialize Alembic** (If not done)
   ```bash
   alembic init alembic
   ```
   *Note: You need to configure `env.py` to import `app.db.base.Base`.*

2. **Generate Migration**
   After modifying `app/models/*.py`:
   ```bash
   alembic revision --autogenerate -m "Description of change"
   ```

3. **Apply Migration**
   ```bash
   alembic upgrade head
   ```

4. **Rollback**
   ```bash
   alembic downgrade -1
   ```

## Best Practices
- Always review the generated migration script in `alembic/versions/` before applying.
- Don't change models without creating a migration.
