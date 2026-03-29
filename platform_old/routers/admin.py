import logging

import psycopg2
import psycopg2.errors
import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from passlib.hash import bcrypt

from platform.db import get_conn
from platform.models import CreateUserRequest, UpdateUserRequest, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def require_admin(request: Request):
    if request.state.role != "admin":
        raise HTTPException(status_code=403, detail="Insufficient permissions")


_SELECT_COLS = "user_id, email, role, status, created_at, last_login"


@router.post("/admin/users", response_model=UserResponse, status_code=201, dependencies=[Depends(require_admin)])
def create_user(request_body: CreateUserRequest):
    password_hash = bcrypt.hash(request_body.password)
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"INSERT INTO users (email, password_hash, role) VALUES (%s, %s, %s)"
                    f" RETURNING {_SELECT_COLS}",
                    (request_body.email, password_hash, request_body.role),
                )
                row = cur.fetchone()
            conn.commit()
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="Email already registered")

    return UserResponse(**row)


@router.get("/admin/users", response_model=list[UserResponse], dependencies=[Depends(require_admin)])
def list_users():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"SELECT {_SELECT_COLS} FROM users ORDER BY created_at"
            )
            rows = cur.fetchall()

    return [UserResponse(**row) for row in rows]


@router.patch("/admin/users/{user_id}", response_model=UserResponse, dependencies=[Depends(require_admin)])
def update_user(user_id: str, request_body: UpdateUserRequest):
    fields = {k: v for k, v in request_body.model_dump().items() if v is not None}
    if not fields:
        # Nothing to update — just return current state
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"SELECT {_SELECT_COLS} FROM users WHERE user_id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="User not found")
        return UserResponse(**row)

    set_clause = ", ".join(f"{col} = %s" for col in fields)
    values = list(fields.values()) + [user_id]

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"UPDATE users SET {set_clause} WHERE user_id = %s RETURNING {_SELECT_COLS}",
                values,
            )
            row = cur.fetchone()
        conn.commit()

    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(**row)


@router.delete("/admin/users/{user_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_user(user_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            deleted = cur.rowcount
        conn.commit()

    if deleted == 0:
        raise HTTPException(status_code=404, detail="User not found")

    return Response(status_code=204)


@router.get("/admin/activity", dependencies=[Depends(require_admin)])
def get_activity(
    user_id: str | None = None,
    action: str | None = None,
    limit: int = 100,
):
    """
    Return paginated user activity logs.
    Optional filters: ?user_id=&action=&limit=
    """
    conditions = []
    params: list = []

    if user_id:
        conditions.append("user_id = %s")
        params.append(user_id)
    if action:
        conditions.append("action = %s")
        params.append(action)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(max(1, min(limit, 1000)))  # clamp limit

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"SELECT user_id, action, timestamp, ip_address "
                f"FROM user_activity {where} "
                f"ORDER BY timestamp DESC LIMIT %s",
                params,
            )
            rows = cur.fetchall()

    return {"logs": [dict(r) for r in rows]}
