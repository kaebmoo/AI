from app.services.ai.response_utils import extract_sql


def test_plain_cte_is_extracted_whole():
    # Regression: bare WITH ... was previously truncated to "SELECT 1) SELECT ..."
    text = "WITH cte AS (SELECT 1) SELECT * FROM cte;"
    assert extract_sql(text) == "WITH cte AS (SELECT 1) SELECT * FROM cte;"


def test_fenced_cte_is_extracted():
    text = "```sql\nWITH c AS (SELECT 1) SELECT * FROM c\n```"
    assert extract_sql(text) == "WITH c AS (SELECT 1) SELECT * FROM c"


def test_plain_select_still_works():
    assert extract_sql("SELECT 1;") == "SELECT 1;"


def test_no_sql_returns_none():
    assert extract_sql("no query here") is None
