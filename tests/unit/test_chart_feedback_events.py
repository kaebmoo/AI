import json

from app.api.v1.chat import _log_chart_feedback_event
from app.models.feedback_models import ChartFeedbackEvent


def test_chart_switch_logs_profile_decision_and_request(db_session):
    data = [
        {"account": f"A{i}", "month": str(month), "amount": i * month}
        for i in range(8)
        for month in range(1, 13)
    ]

    _log_chart_feedback_event(
        db=db_session,
        conversation_id="conv-chart",
        user_id=None,
        question="เปลี่ยนเป็นกราฟแท่งแนวนอน",
        intent={"requested_type": "horizontal_bar"},
        prev_config={
            "category_column": "account",
            "series_column": "month",
            "measure_column": "amount",
            "visualization": "heatmap",
            "title": "ค่าใช้จ่ายรายเดือน",
        },
        enriched={
            "visualization": "heatmap",
            "chart_config": {
                "category_column": "account",
                "series_column": "month",
                "measure_column": "amount",
                "max_series": 5,
            },
        },
        data=data,
    )

    event = db_session.query(ChartFeedbackEvent).one()
    assert event.question == "เปลี่ยนเป็นกราฟแท่งแนวนอน"
    assert event.requested_type == "horizontal_bar"
    assert event.resolved_type == "heatmap"
    assert event.requested_type_vetoed is True

    profile = json.loads(event.profile_json)
    decision = json.loads(event.decision_json)
    assert profile["row_count"] == 96
    assert profile["matrix_shape"]["kind"] == "time_matrix"
    assert decision["visualization"] == "heatmap"
    assert "19 หมวด" not in (decision["warning"] or "")
