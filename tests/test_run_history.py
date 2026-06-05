from pathlib import Path

from finance_news_tracker.store import Store


def test_run_history_lifecycle(tmp_path: Path):
    store = Store(tmp_path / "test.db")
    history_id = store.create_run_history(
        run_id="20260605_100000",
        trigger_type="scheduled",
        llm_model="deepseek-chat",
    )
    store.finish_run_history(
        history_id,
        status="success",
        markdown_path="/app/summaries/report.md",
        docx_path="/app/summaries/report.docx",
        email_sent=True,
        email_recipients="a@example.com, b@example.com",
        source_count=10,
        story_count=5,
    )

    with store._conn() as conn:
        row = conn.execute(
            "SELECT * FROM run_history WHERE id = ?",
            (history_id,),
        ).fetchone()

    assert row["status"] == "success"
    assert row["email_sent"] == 1
    assert row["email_recipients"] == "a@example.com, b@example.com"
    assert row["story_count"] == 5
    assert row["finished_at"] is not None
