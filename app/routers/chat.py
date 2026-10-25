from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from openai import OpenAIError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..dependencies import current_user, get_db
from ..models import ChatMessage, Task, User, now_utc
from ..schemas import ChatIn, ChatMessageOut, ChatOut
from ..task_service import visible_tasks_query

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/history", response_model=list[ChatMessageOut])
def chat_history(db: Session = Depends(get_db), user: User = Depends(current_user)):
    messages = db.scalars(select(ChatMessage).where(ChatMessage.user_id == user.id)
                          .order_by(ChatMessage.id.desc()).limit(20)).all()
    return list(reversed(messages))


@router.post("", response_model=ChatOut)
def chat(payload: ChatIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    settings = request.app.state.settings
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
    tasks = db.scalars(visible_tasks_query(user.id).order_by(Task.id.desc()).limit(50)).all()
    history = db.scalars(select(ChatMessage).where(ChatMessage.user_id == user.id)
                         .order_by(ChatMessage.id.desc()).limit(6)).all()
    try:
        reply = request.app.state.chat_provider(
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
