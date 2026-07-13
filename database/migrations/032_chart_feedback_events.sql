-- ============================================================
-- Migration 032: Chart feedback events for chart-switch telemetry
-- ============================================================

CREATE TABLE IF NOT EXISTS chart_feedback_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    user_id INTEGER,
    question TEXT NOT NULL,
    requested_type TEXT,
    resolved_type TEXT,
    requested_type_accepted INTEGER DEFAULT 0,
    requested_type_vetoed INTEGER DEFAULT 0,
    profile_json TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_chart_feedback_events_conversation_id
    ON chart_feedback_events(conversation_id);

CREATE INDEX IF NOT EXISTS ix_chart_feedback_events_conversation_created
    ON chart_feedback_events(conversation_id, created_at);
