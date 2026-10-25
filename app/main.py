from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .ai_service import ask_demo, ask_openai
from .config import Settings, get_settings
from .database import Base, make_session_factory
from .middleware import check_request_origin
from .routers import auth, chat, system, tasks

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(app.state.engine)
    yield
    app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Task Manager AI", version="1.0.0", lifespan=lifespan)
    engine, session_factory = make_session_factory(settings.database_url)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.settings = settings
    app.state.chat_provider = ask_demo if settings.ai_mode == "demo" else ask_openai

    app.middleware("http")(check_request_origin)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(tasks.router)
    app.include_router(chat.router)
    return app


app = create_app()
