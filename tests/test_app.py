import pytest
from fastapi.testclient import TestClient

from app import ai_service
from app.config import Settings
from app.database import Base, make_session_factory
from app.main import create_app


@pytest.fixture
def app(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", ai_mode="demo", ai_max_requests_per_hour=2)
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    return app


def account(app, name: str, email: str) -> TestClient:
    client = TestClient(app)
    response = client.post("/api/auth/register", json={"name": name, "email": email, "password": "password1234"})
    assert response.status_code == 201
    response = client.post("/api/auth/login", json={"email": email, "password": "password1234"})
    assert response.status_code == 200
    return client


def test_registration_login_and_task_permissions(app):
    owner = account(app, "Lan", "lan@example.com")
    worker = account(app, "Minh", "minh@example.com")
    outsider = account(app, "Hoa", "hoa@example.com")
    worker_id = worker.get("/api/auth/me").json()["id"]
    created = owner.post("/api/tasks", json={"title": "Báo cáo tuần", "assignee_id": worker_id, "priority": "high"})
    assert created.status_code == 201
    task_id = created.json()["id"]

    assert worker.get("/api/tasks").json()[0]["title"] == "Báo cáo tuần"
    assert outsider.get(f"/api/tasks/{task_id}").status_code == 404
    assert worker.patch(f"/api/tasks/{task_id}", json={"title": "Sửa lén"}).status_code == 403
    assert worker.patch(f"/api/tasks/{task_id}", json={"status": "doing"}).json()["status"] == "doing"
    assert worker.delete(f"/api/tasks/{task_id}").status_code == 403
    assert owner.delete(f"/api/tasks/{task_id}").status_code == 204
    assert worker.get(f"/api/tasks/{task_id}").status_code == 404


def test_auth_validation_and_logout(app):
    anonymous = TestClient(app)
    assert anonymous.get("/api/tasks").status_code == 401
    assert anonymous.post("/api/auth/register", json={"name": "  ", "email": "wrong", "password": "short"}).status_code == 422
    user = account(app, "Lan", "lan@example.com")
    assert user.post("/api/auth/register", json={"name": "Lan", "email": "lan@example.com", "password": "password1234"}).status_code == 409
    assert user.post("/api/auth/login", json={"email": "lan@example.com", "password": "incorrect"}).status_code == 401
    assert user.post("/api/auth/logout").status_code == 204
    assert user.get("/api/auth/me").status_code == 401


def test_chat_only_receives_visible_tasks_and_has_limit(app):
    lan = account(app, "Lan", "lan@example.com")
    minh = account(app, "Minh", "minh@example.com")
    lan.post("/api/tasks", json={"title": "Việc của Lan"})
    minh.post("/api/tasks", json={"title": "Việc của Minh"})
    seen = []

    def fake_provider(message, history, tasks, **kwargs):
        seen.append(([task.title for task in tasks], [item.content for item in history]))
        return f"Đã nhận: {message}"

    app.state.chat_provider = fake_provider
    assert lan.post("/api/chat", json={"message": "Việc nào gấp?"}).json()["reply"] == "Đã nhận: Việc nào gấp?"
    assert seen[0][0] == ["Việc của Lan"]
    assert len(lan.get("/api/chat/history").json()) == 2
    assert minh.get("/api/chat/history").json() == []
    assert lan.post("/api/chat", json={"message": "Còn gì nữa?"}).status_code == 200
    assert seen[1][1] == ["Việc nào gấp?", "Đã nhận: Việc nào gấp?"]
    assert lan.post("/api/chat", json={"message": "Lần ba"}).status_code == 429


def test_chat_needs_key_in_openai_mode(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'no-key.db'}", ai_mode="openai"))
    Base.metadata.create_all(app.state.engine)
    user = account(app, "Lan", "lan@example.com")
    response = user.post("/api/chat", json={"message": "Xin chào"})
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_openai_adapter_uses_responses_api_and_bounded_context(monkeypatch):
    captured = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return type("Result", (), {"output_text": "  Gợi ý hoàn thành việc.  "})()

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.responses = FakeResponses()

    monkeypatch.setattr(ai_service, "OpenAI", FakeClient)
    reply = ai_service.ask_openai("Hôm nay làm gì?", [], [], api_key="test-key", model="test-model")
    assert reply == "Gợi ý hoàn thành việc."
    assert captured["model"] == "test-model"
    assert captured["store"] is False
    assert captured["client"]["api_key"] == "test-key"
    assert "Chưa có công việc nào" in captured["input"][-1]["content"]


def test_static_page_and_origin_check(app):
    client = TestClient(app)
    assert "TaskFlow AI" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    response = client.post(
        "/api/auth/logout",
        headers={"Origin": "https://other.example"},
    )
    assert response.status_code == 403


def test_supabase_url_uses_psycopg_driver_without_connecting():
    engine, _ = make_session_factory(
        "postgresql://postgres.ref:password@pooler.example.com:5432/postgres?sslmode=require"
    )
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.query["sslmode"] == "require"
    finally:
        engine.dispose()


def test_startup_creates_tables(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'startup.db'}", ai_mode="demo"))
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/register",
            json={"name": "Lan", "email": "lan@example.com", "password": "password1234"},
        )
        assert response.status_code == 201
