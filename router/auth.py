import hashlib
import os
import secrets
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Annotated

import bcrypt
import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from database import get_db
from models import PasswordResets, RefreshTokens, Users
from schemas import (ForgotPasswordRequest, Message, RefreshRequest, ResetPasswordRequest,
                     SignupRequest, TokenPair, UserOut)

router = APIRouter(prefix='/auth', tags=['auth'])

# Production e ei gulo environment variable theke nao
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 7
RESET_TOKEN_MINUTES = 30
DEBUG = os.getenv("DEBUG", "true").lower() == "true"
FRONTEND_RESET_URL = os.getenv("FRONTEND_RESET_URL", "http://localhost:5173/reset-password")

oauth2_bearer = OAuth2PasswordBearer(tokenUrl='auth/login')
db_dependency = Annotated[Session, Depends(get_db)]


# ---------------- helpers ----------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except ValueError:
        return False


def create_token(user_id: int, token_type: str, expires_delta: timedelta, jti: str | None = None) -> str:
    now = datetime.now(timezone.utc)  # JWT claim gulo UTC te thakte hobe (naive local time dile expiry bhul hoy)
    payload = {'sub': str(user_id), 'type': token_type, 'jti': jti or uuid.uuid4().hex,
               'iat': now, 'exp': now + expires_delta}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: str) -> dict:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get('type') != expected_type:
        raise jwt.InvalidTokenError('Wrong token type')
    return payload


def issue_tokens(db: Session, user: Users) -> TokenPair:
    jti = uuid.uuid4().hex
    access_delta = timedelta(minutes=ACCESS_TOKEN_MINUTES)
    refresh_delta = timedelta(days=REFRESH_TOKEN_DAYS)
    db.add(RefreshTokens(jti=jti, user_id=user.id, expires_at=datetime.now() + refresh_delta))
    db.commit()
    return TokenPair(
        access_token=create_token(user.id, 'access', access_delta),
        refresh_token=create_token(user.id, 'refresh', refresh_delta, jti=jti),
        expires_in=int(access_delta.total_seconds()),
    )


def send_email(to: str, subject: str, body: str):
    host = os.getenv("SMTP_HOST")
    if not host:  # dev mode: console e print hobe
        print(f"\n--- EMAIL (dev) ---\nTo: {to}\nSubject: {subject}\n\n{body}\n-------------------\n")
        return
    msg = EmailMessage()
    msg['From'], msg['To'], msg['Subject'] = os.getenv("MAIL_FROM", "no-reply@dispatch.local"), to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=10) as server:
            server.starttls()
            if os.getenv("SMTP_USER"):
                server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
            server.send_message(msg)
    except Exception as e:
        print("Email send failed:", e)


# ---------------- dependencies (main.py / admin.py te use hobe) ----------------
async def get_current_user(token: Annotated[str, Depends(oauth2_bearer)], db: db_dependency) -> dict:
    headers = {'WWW-Authenticate': 'Bearer'}
    try:
        payload = decode_token(token, 'access')
    except jwt.ExpiredSignatureError:
        # frontend ei 401 dhorle /auth/refresh call korbe
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Token expired', headers=headers)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token', headers=headers)

    user = db.query(Users).filter(Users.id == int(payload['sub'])).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User not found or inactive', headers=headers)
    return {'id': user.id, 'username': user.username, 'role': user.role}


user_dependency = Annotated[dict, Depends(get_current_user)]


async def get_admin_user(user: user_dependency) -> dict:
    if user.get('role') != 'admin':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Admin access required')
    return user


admin_dependency = Annotated[dict, Depends(get_admin_user)]


# ---------------- routes ----------------
@router.post('/signup', response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: db_dependency):
    email = body.email.lower()
    if db.query(Users).filter(or_(Users.email == email, Users.username == body.username)).first():
        raise HTTPException(status_code=409, detail='Email or username already registered')
    # Public signup e sob shomoy 'user' role. Admin seed kora hoy ba onno admin banay.
    user = Users(email=email, username=body.username, firstname=body.firstname, lastname=body.lastname,
                 phone=body.phone, hash_password=hash_password(body.password), role='user')
    db.add(user)
    db.commit()
    return user


@router.post('/login', response_model=TokenPair)
def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: db_dependency):
    """form er `username` field e email ba username duita-i dewa jabe."""
    ident = form_data.username.strip()
    user = db.query(Users).filter(or_(Users.email == ident.lower(), Users.username == ident)).first()
    if not user or not verify_password(form_data.password, user.hash_password):
        raise HTTPException(status_code=401, detail='Incorrect email/username or password',
                            headers={'WWW-Authenticate': 'Bearer'})
    if not user.is_active:
        raise HTTPException(status_code=403, detail='Account is disabled')
    return issue_tokens(db, user)


@router.post('/refresh', response_model=TokenPair)
def refresh(body: RefreshRequest, db: db_dependency):
    try:
        payload = decode_token(body.refresh_token, 'refresh')
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail='Refresh token expired, please log in again')
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail='Invalid refresh token')

    record = db.query(RefreshTokens).filter(RefreshTokens.jti == payload['jti']).first()
    if record is None:
        raise HTTPException(status_code=401, detail='Invalid refresh token')
    if record.revoked:
        # purano token abar use hoyeche -> chori dhore niye oi user er sob session bondho
        db.execute(update(RefreshTokens).where(RefreshTokens.user_id == record.user_id).values(revoked=True))
        db.commit()
        raise HTTPException(status_code=401, detail='Refresh token already used, please log in again')

    user = db.query(Users).filter(Users.id == record.user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail='User not found or inactive')

    record.revoked = True  # rotation: ek refresh token ek bar-i use hobe
    return issue_tokens(db, user)


@router.post('/logout', status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshRequest, db: db_dependency):
    try:
        payload = decode_token(body.refresh_token, 'refresh')
    except jwt.InvalidTokenError:
        return
    db.execute(update(RefreshTokens).where(RefreshTokens.jti == payload['jti']).values(revoked=True))
    db.commit()


@router.get('/me', response_model=UserOut)
def me(user: user_dependency, db: db_dependency):
    return db.query(Users).filter(Users.id == user['id']).first()


@router.post('/forgot-password', response_model=Message)
def forgot_password(body: ForgotPasswordRequest, background: BackgroundTasks, db: db_dependency):
    generic = 'If that email is registered, a password reset link has been sent.'
    user = db.query(Users).filter(Users.email == body.email.lower()).first()
    if not user or not user.is_active:
        return Message(message=generic)  # email ache ki nai bujhte dewa hobe na

    db.execute(update(PasswordResets).where(PasswordResets.user_id == user.id, PasswordResets.used.is_(False)).values(used=True))
    raw = secrets.token_urlsafe(32)
    db.add(PasswordResets(user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                          expires_at=datetime.now() + timedelta(minutes=RESET_TOKEN_MINUTES)))
    db.commit()

    link = f"{FRONTEND_RESET_URL}?token={raw}"
    background.add_task(send_email, user.email, 'Reset your password',
                        f"Hi {user.firstname},\n\nReset your password (valid {RESET_TOKEN_MINUTES} minutes):\n{link}\n\nIf this wasn't you, ignore this email.")
    return Message(message=generic, reset_token=raw if DEBUG else None)


@router.post('/reset-password', response_model=Message)
def reset_password(body: ResetPasswordRequest, db: db_dependency):
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    record = db.query(PasswordResets).filter(PasswordResets.token_hash == token_hash).first()
    if record is None or record.used or record.expires_at < datetime.now():
        raise HTTPException(status_code=400, detail='Invalid or expired reset token')

    user = db.query(Users).filter(Users.id == record.user_id).first()
    user.hash_password = hash_password(body.new_password)
    record.used = True
    db.execute(update(RefreshTokens).where(RefreshTokens.user_id == user.id).values(revoked=True))  # sob jaygay logout
    db.commit()
    return Message(message='Password has been reset. You can now log in.')
