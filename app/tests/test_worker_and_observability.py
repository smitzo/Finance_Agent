from types import SimpleNamespace

from app.agent.checkpoint import checkpoint_database_url
from app.worker import tasks


def test_checkpoint_database_url_converts_asyncpg_and_ssl() -> None:
    result = checkpoint_database_url(
        "postgresql+asyncpg://user:pass@db:5432/freight?ssl=require&channel_binding=require"
    )

    assert result == "postgresql://user:pass@db:5432/freight?sslmode=require"


def test_checkpoint_database_url_preserves_unix_socket_uri() -> None:
    result = checkpoint_database_url(
        "postgresql+asyncpg:///freight?host=/var/run/postgresql"
    )

    assert result == "postgresql:///freight?host=%2Fvar%2Frun%2Fpostgresql"


def test_enqueue_bill_returns_celery_task_id(monkeypatch) -> None:
    captured = {}

    def fake_delay(*args):
        captured["args"] = args
        return SimpleNamespace(id="task-123")

    monkeypatch.setattr(tasks.process_bill_task, "delay", fake_delay)

    task_id = tasks.enqueue_bill("FB-1", {"tenant_id": "acme"}, "corr-1")

    assert task_id == "task-123"
    assert captured["args"] == ("FB-1", {"tenant_id": "acme"}, "corr-1")


def test_enqueue_review_resume_returns_celery_task_id(monkeypatch) -> None:
    captured = {}

    def fake_delay(*args):
        captured["args"] = args
        return SimpleNamespace(id="task-456")

    monkeypatch.setattr(tasks.resume_bill_task, "delay", fake_delay)

    task_id = tasks.enqueue_review_resume(
        "FB-1", "acme", "thread-acme-FB-1", "approve", "verified", "corr-2"
    )

    assert task_id == "task-456"
    assert captured["args"][-1] == "corr-2"
