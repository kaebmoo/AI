"""Plan 8.1 — the writers that never ran (owner 2026-09-21: bring them under the rule and point them at config.db).

The learner, a user's SQL correction from the chat, an admin's feedback review and an admin's thumbs-up all wrote
golden_examples / schema_semantic_mapping through the app.db session, which has neither table. Now: what the
learner or a user found waits for a person (learned / proposed); what an admin decided is theirs (manual / active).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.services.auto_analyzer import AnalysisResult, AutoAnalyzer, SuggestedFix
from app.services.scheduler import BackgroundScheduler
from tests.unit import knowledge_db

SEED = """
INSERT INTO schema_semantic_mapping (keyword, target_column, target_condition) VALUES ('นป.', 'division', '= ''นป.''');
INSERT INTO golden_examples (question_pattern, expected_sql, category, is_active, added_by)
    VALUES ('รายได้รายสายงาน', 'SELECT admin', 'revenue', 1, 1);
"""


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "config.db"
    engine = knowledge_db.make(path, SEED)
    return path, sessionmaker(bind=engine)()


@pytest.fixture
def app_db(tmp_path):
    import app.models.chat  # noqa: F401 — register the app tables on Base
    import app.models.feedback_models  # noqa: F401
    import app.models.user  # noqa: F401
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _fix(keyword, confidence, fix_type="add_mapping"):
    return SuggestedFix(fix_type=fix_type, params={"keyword": keyword, "target_column": "UNKNOWN"},
                        confidence=confidence, reason="failed questions", source_query_ids=[1])


def test_what_the_learner_finds_waits_for_a_person_however_sure(config):
    path, session = config
    result = AnalysisResult(total_failures=3, groups=[], suggested_fixes=[
        _fix("ftth", 0.95), _fix("นป.", 0.5), _fix("rule", 0.99, fix_type="add_rule")])
    scheduler = BackgroundScheduler(db_factory=MagicMock)
    for _ in range(2):
        scheduler._propose_fixes(result, MagicMock(), session)
    assert knowledge_db.rows(path, "SELECT keyword, target_column, source, status, confidence "
                                   "FROM schema_semantic_mapping ORDER BY keyword") == [
        ("ftth", "UNKNOWN", "learned", "proposed", 0.95),   # 0.95 used to mean "in use now"
        ("นป.", "division", "manual", "active", None)]       # a person's keyword keeps its mapping…
    assert knowledge_db.rows(path, "SELECT row_key, source, confidence FROM knowledge_proposals") == [
        ('{"keyword": "นป."}', "learned", 0.5)]               # …and the learner's waits, once
    assert knowledge_db.rows(path, "SELECT count(*) FROM schema_business_rules") == [(0,)]
    assert knowledge_db.rows(path, "SELECT is_active FROM schema_semantic_mapping WHERE keyword = 'ftth'") == [(0,)]


def test_the_learners_keyword_check_reads_the_config_db(config, app_db):
    _, session = config
    analyzer = AutoAnalyzer(app_db, config_db=session)
    assert analyzer._keyword_not_mapped("นป.") is False
    assert analyzer._keyword_not_mapped("ไม่มีใครรู้จัก") is True


def test_a_users_correction_waits_and_never_touches_an_admins_example(config):
    from app.api.v1.chat import save_training
    path, session = config
    save_training(session, "รายได้รายสายงาน", "SELECT user", "revenue", user_id=7, is_admin=False)
    save_training(session, "คำถามใหม่", "SELECT user", "revenue", user_id=7, is_admin=False)
    save_training(session, "คำถามใหม่", "SELECT user2", "revenue", user_id=8, is_admin=False)  # newer one waits
    assert knowledge_db.rows(path, "SELECT question_pattern, expected_sql, is_active, source, status "
                                   "FROM golden_examples ORDER BY id") == [
        ("รายได้รายสายงาน", "SELECT admin", 1, "manual", "active"),   # it used to be switched off and overwritten
        ("คำถามใหม่", "SELECT user2", 0, "learned", "proposed")]
    assert knowledge_db.rows(path, "SELECT source FROM knowledge_proposals") == [("learned",)]
    save_training(session, "คำถามใหม่", "SELECT admin", "revenue", user_id=1, is_admin=True)  # an admin takes it
    assert knowledge_db.rows(path, "SELECT expected_sql, is_active, source, status FROM golden_examples "
                                   "WHERE question_pattern = 'คำถามใหม่'") == [("SELECT admin", 1, "manual", "active")]


def _chat_with_feedback(app_db):
    from app.models.chat import ChatHistory
    from app.models.feedback_models import FeedbackRating, UserFeedback
    chat = ChatHistory(question="รายได้รวมปี 2568", generated_sql="SELECT SUM(revenue) FROM revenue_search")
    app_db.add(chat)
    app_db.commit()
    feedback = UserFeedback(chat_id=chat.id, rating=FeedbackRating.THUMBS_UP)
    app_db.add(feedback)
    app_db.commit()
    return chat, feedback


def test_an_admins_review_writes_their_example_to_the_config_db(config, app_db):
    from app.services.feedback_service import FeedbackService
    path, session = config
    _, feedback = _chat_with_feedback(app_db)
    FeedbackService(app_db).review_feedback(feedback.id, reviewer_id=1, is_golden_example=True, config_db=session)
    assert knowledge_db.rows(path, "SELECT expected_sql, source, status FROM golden_examples "
                                   "WHERE question_pattern = 'รายได้รวมปี 2568'") == [
        ("SELECT SUM(revenue) FROM revenue_search", "manual", "active")]


def test_an_admins_thumbs_up_is_kept_as_their_example(config, app_db):
    from app.api.v1.feedback import submit_feedback
    from app.models.feedback_models import FeedbackRating
    path, session = config
    chat, _ = _chat_with_feedback(app_db)
    ai_service = MagicMock()
    admin = SimpleNamespace(id=1, role="admin")
    submit_feedback(chat.id, FeedbackRating.THUMBS_UP, None, None, admin, app_db, ai_service, session)
    assert knowledge_db.rows(path, "SELECT expected_sql, source, status FROM golden_examples "
                                   "WHERE question_pattern = 'รายได้รวมปี 2568'") == [
        ("SELECT SUM(revenue) FROM revenue_search", "manual", "active")]  # survives the next Sync Brain
    ai_service.train.assert_called_once()


def test_a_users_correction_never_changes_an_example_in_use(config):
    """may_replace let `learned` rewrite a machine's example that was already in use (Codex review 2026-09-22)."""
    from sqlalchemy import text

    from app.api.v1.chat import save_training
    path, session = config
    session.execute(text("INSERT INTO golden_examples (question_pattern, expected_sql, category, is_active, source, "
                         "status) VALUES ('คำถามของเครื่อง', 'SELECT 1', 'revenue', 1, 'inferred', 'active')"))
    session.commit()
    save_training(session, "คำถามของเครื่อง", "SELECT 99", "revenue", user_id=7, is_admin=False)
    assert knowledge_db.rows(path, "SELECT expected_sql, is_active, source, status FROM golden_examples "
                                   "WHERE question_pattern = 'คำถามของเครื่อง'") == [("SELECT 1", 1, "inferred", "active")]
    assert knowledge_db.rows(path, "SELECT row_key, source FROM knowledge_proposals") == [
        ('{"question_pattern": "คำถามของเครื่อง"}', "learned")]
