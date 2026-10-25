import hashlib
import secrets
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAIError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .ai_service import ask_demo, ask_openai
from .config import Settings, get_settings
from .database import Base, make_session_factory
from .dependencies import current_user, get_db
from .models import ChatMessage, LoginSession, Task, User, now_utc
from .schemas import ChatIn, ChatMessageOut, ChatOut, LoginIn, RegisterIn, TaskCreate, TaskOut, TaskUpdate, UserOut

password_hasher = PasswordHasher()
SESSION_DAYS = 7
STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Task Manager AI", version="1.0.0")
    engine, session_factory = make_session_factory(settings.database_url)
    Base.metadata.create_all(engine)
    app.state.session_factory = session_factory
    app.state.settings = settings
    app.state.chat_provider = ask_demo if settings.ai_mode == "demo" else ask_openai
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def check_request_origin(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin:
                parsed = urlsplit(origin)
                if (parsed.scheme, parsed.netloc) != (request.url.scheme, request.url.netloc):
                    return Response(status_code=403, content="Nguồn yêu cầu không hợp lệ")
            elif request.headers.get("sec-fetch-site") == "cross-site":
                return Response(status_code=403, content="Nguồn yêu cầu không hợp lệ")
        return await call_next(request)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "ai_mode": settings.ai_mode}

    @app.post("/api/auth/register", response_model=UserOut, status_code=201)
    def register(payload: RegisterIn, db: Session = Depends(get_db)):
        user = User(name=payload.name, email=str(payload.email).lower(), password_hash=password_hasher.hash(payload.password))
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Email đã được đăng ký") from None
        db.refresh(user)
        return user

    @app.post("/api/auth/login", response_model=UserOut)
    def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
        user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
        try:
            valid = user is not None and password_hasher.verify(user.password_hash, payload.password)
        except VerifyMismatchError:
            valid = False
        if not valid:
            raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")
        token = secrets.token_urlsafe(32)
        db.add(LoginSession(
            user_id=user.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=now_utc() + timedelta(days=SESSION_DAYS),
        ))
        db.commit()
        response.set_cookie(
            key="task_session", value=token, max_age=SESSION_DAYS * 86400,
            httponly=True, secure=settings.cookie_secure, samesite="lax", path="/api",
        )
        return user

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response, db: Session = Depends(get_db)):
        token = request.cookies.get("task_session")
        if token:
            login_session = db.scalar(select(LoginSession).where(
                LoginSession.token_hash == hashlib.sha256(token.encode()).hexdigest()
            ))
            if login_session:
                db.delete(login_session)
                db.commit()
        response.delete_cookie("task_session", path="/api")

    @app.get("/api/auth/me", response_model=UserOut)
    def me(user: User = Depends(current_user)):
        return user

    @app.get("/api/users")
    def users(db: Session = Depends(get_db), _: User = Depends(current_user)):
        return [{"id": user.id, "name": user.name} for user in db.scalars(select(User).order_by(User.name)).all()]

    def visible_task(task_id: int, db: Session, user: User) -> Task:
        task = db.get(Task, task_id)
        if task is None or user.id not in (task.created_by_id, task.assignee_id):
            raise HTTPException(status_code=404, detail="Không tìm thấy công việc")
        return task

    @app.get("/api/tasks", response_model=list[TaskOut])
    def list_tasks(db: Session = Depends(get_db), user: User = Depends(current_user)):
        return db.scalars(select(Task).where(or_(
            Task.created_by_id == user.id, Task.assignee_id == user.id
        )).order_by(Task.created_at.desc(), Task.id.desc())).all()

    @app.post("/api/tasks", response_model=TaskOut, status_code=201)
    def create_task(payload: TaskCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
        assignee_id = payload.assignee_id or user.id
        if db.get(User, assignee_id) is None:
            raise HTTPException(status_code=422, detail="Người được giao không tồn tại")
        task = Task(
            title=payload.title.strip(), description=payload.description,
            priority=payload.priority.value, due_date=payload.due_date,
            created_by_id=user.id, assignee_id=assignee_id,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    @app.get("/api/tasks/{task_id}", response_model=TaskOut)
    def get_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
        return visible_task(task_id, db, user)

    @app.patch("/api/tasks/{task_id}", response_model=TaskOut)
    def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
        task = visible_task(task_id, db, user)
        changes = payload.model_dump(exclude_unset=True)
        if user.id != task.created_by_id and set(changes) != {"status"}:
            raise HTTPException(status_code=403, detail="Người được giao chỉ được đổi trạng thái")
        for field, value in changes.items():
            if field != "due_date" and value is None:
                raise HTTPException(status_code=422, detail=f"{field} không được để trống")
            if field == "assignee_id" and db.get(User, value) is None:
                raise HTTPException(status_code=422, detail="Người được giao không tồn tại")
            if field in ("status", "priority"):
                value = value.value
            setattr(task, field, value)
        task.updated_at = now_utc()
        db.commit()
        db.refresh(task)
        return task

    @app.delete("/api/tasks/{task_id}", status_code=204)
    def delete_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
        task = visible_task(task_id, db, user)
        if task.created_by_id != user.id:
            raise HTTPException(status_code=403, detail="Chỉ người tạo được xóa công việc")
        db.delete(task)
        db.commit()

    @app.get("/api/chat/history", response_model=list[ChatMessageOut])
    def chat_history(db: Session = Depends(get_db), user: User = Depends(current_user)):
        messages = db.scalars(select(ChatMessage).where(ChatMessage.user_id == user.id)
                              .order_by(ChatMessage.id.desc()).limit(20)).all()
        return list(reversed(messages))

    @app.post("/api/chat", response_model=ChatOut)
    def chat(payload: ChatIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
        if settings.ai_mode != "demo" and not settings.openai_api_key:
            raise HTTPException(status_code=503, detail="Chưa cấu hình OPENAI_API_KEY")
        hour_ago = now_utc() - timedelta(hours=1)
        calls = db.scalar(select(func.count(ChatMessage.id)).where(
            ChatMessage.user_id == user.id,
            ChatMessage.role == "user",
            ChatMessage.created_at >= hour_ago,
        ))
        if calls >= settings.ai_max_requests_per_hour:
            raise HTTPException(status_code=429, detail="Đã đạt giới hạn chatbot trong một giờ")
        tasks = db.scalars(select(Task).where(or_(
            Task.created_by_id == user.id, Task.assignee_id == user.id
        )).order_by(Task.id.desc()).limit(50)).all()
        history = db.scalars(select(ChatMessage).where(ChatMessage.user_id == user.id)
                             .order_by(ChatMessage.id.desc()).limit(6)).all()
        try:
            reply = app.state.chat_provider(
                payload.message, list(reversed(history)), tasks,
                api_key=settings.openai_api_key, model=settings.openai_model,
            )
        except (OpenAIError, RuntimeError):
            raise HTTPException(status_code=502, detail="Dịch vụ AI tạm thời không khả dụng") from None
        db.add_all([
            ChatMessage(user_id=user.id, role="user", content=payload.message),
            ChatMessage(user_id=user.id, role="assistant", content=reply),
        ])
        db.commit()
        return ChatOut(reply=reply)

    return app


app = create_app()
