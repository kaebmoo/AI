from sqlalchemy.ext.declarative import declarative_base

# App DB tables (users, sessions, chats, feedback, etc.)
Base = declarative_base()

# Config DB tables (schema_contexts, mappings, rules, hierarchy, etc.)
# Separate base so init_db doesn't create config tables in app.db
ConfigBase = declarative_base()
