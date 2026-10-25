from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..dependencies import current_user, get_db
from ..models import User
from ..schemas import LoginIn, RegisterIn, UserOut
from ..security import COOKIE_NAME, SESSION_DAYS, create_login_session, hash_password, revoke_login_session, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    user = User(name=payload.name, email=str(payload.email).lower(), password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email đã được đăng ký") from None
    db.refresh(user)
    return user


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is None or not verify_password(user.password_hash, payload.password):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")
    token = create_login_session(db, user)
    response.set_cookie(
        key=COOKIE_NAME, value=token, max_age=SESSION_DAYS * 86400,
        httponly=True, secure=request.app.state.settings.cookie_secure,
        samesite="lax", path="/api",
    )
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    revoke_login_session(db, request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME, path="/api")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
