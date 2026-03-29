import os
import threading
import logging
from datetime import datetime, timedelta

import jwt
from fastapi import APIRouter, Request, HTTPException
from passlib.hash import bcrypt

from platform.models import LoginRequest, TokenResponse
from platform.db import get_conn

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory failed login attempt counter: email -> (count, window_start)
_attempts: dict[str, tuple[int, datetime]] = {}
_attempts_lock = threading.Lock()

_LOCKOUT_THRESHOLD = 5
_LOCKOUT_WINDOW = timedelta(minutes=15)


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _log_activity(user_id, action, ip):
    def _write():
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO user_activity (user_id, action, ip_address) VALUES (%s, %s, %s)",
                        (user_id, action, ip),
                    )
                conn.commit()
        except Exception as e:
            logger.error(f"activity log failed: {e}")

    threading.Thread(target=_write, daemon=True).start()


def _increment_attempt(email: str) -> int:
    """Increment the failed attempt counter for email. Returns new count."""
    with _attempts_lock:
        now = datetime.utcnow()
        if email in _attempts:
            count, window_start = _attempts[email]
            if now - window_start <= _LOCKOUT_WINDOW:
                count += 1
            else:
                # Window expired — reset
                count = 1
                window_start = now
        else:
            count = 1
            window_start = now
        _attempts[email] = (count, window_start)
        return count


def _reset_attempt(email: str) -> None:
    with _attempts_lock:
        _attempts.pop(email, None)


@router.post("/auth/login", response_model=TokenResponse)
def login(request_body: LoginRequest, request: Request):
    ip = _get_client_ip(request)

    # 1. Look up user by email
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, password_hash, role, status FROM users WHERE email = %s",
                (request_body.email,),
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_id, password_hash, role, status = row

    # 2. Check if account is locked
    if status == "locked":
        raise HTTPException(status_code=423, detail="Account locked. Try again later.")

    # 3. Verify password
    password_valid = bcrypt.verify(request_body.password, password_hash)

    if not password_valid:
        # 4. On failure: increment attempt counter
        count = _increment_attempt(request_body.email)

        # Fire-and-forget failed_login activity log
        _log_activity(str(user_id), "failed_login", ip)

        if count >= _LOCKOUT_THRESHOLD:
            # Lock the account in DB
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE users SET status = 'locked' WHERE email = %s",
                        (request_body.email,),
                    )
                conn.commit()
            raise HTTPException(status_code=423, detail="Account locked. Try again later.")

        raise HTTPException(status_code=401, detail="Invalid credentials")

    # 5. On success
    _reset_attempt(request_body.email)

    # Update last_login
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET last_login = now() WHERE user_id = %s",
                (str(user_id),),
            )
        conn.commit()

    # Fire-and-forget login activity log
    _log_activity(str(user_id), "login", ip)

    # Issue JWT
    payload = {
        "user_id": str(user_id),
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=24),
    }
    token = jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")

    return TokenResponse(access_token=token)


@router.post("/auth/logout")
def logout(request: Request):
    """
    Stateless JWT logout.
    Logs the logout event in user_activity and returns success.
    Token invalidation is client-side (stateless JWT).
    """
    ip = _get_client_ip(request)
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        _log_activity(str(user_id), "logout", ip)
    return {"message": "Logout successful"}
