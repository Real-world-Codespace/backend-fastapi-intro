from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import LoginSession, User, now_utc
from .security import COOKIE_NAME, hash_token


def get_db(request: Request):
    with request.app.state.session_factory() as db:
        yield db


def current_user(
    session: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Cần đăng nhập")
    token_hash = hash_token(session)
    login = db.scalar(select(LoginSession).where(LoginSession.token_hash == token_hash))
    if login is None or login.expires_at <= now_utc():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Phiên đăng nhập hết hạn")
    user = db.get(User, login.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản không tồn tại")
    return user
