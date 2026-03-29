from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr
from pydantic import UUID4


class LoginRequest(BaseModel):
    model_config = {"extra": "forbid"}

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    user_id: UUID4
    email: EmailStr
    role: Literal["admin", "analyst", "viewer"]
    status: Literal["active", "locked"]
    created_at: datetime
    last_login: Optional[datetime] = None


class CreateUserRequest(BaseModel):
    model_config = {"extra": "forbid"}

    email: EmailStr
    password: str
    role: Literal["admin", "analyst", "viewer"]


class UpdateUserRequest(BaseModel):
    model_config = {"extra": "forbid"}

    email: Optional[EmailStr] = None
    role: Optional[Literal["admin", "analyst", "viewer"]] = None
    status: Optional[Literal["active", "locked"]] = None


class DashboardResponse(BaseModel):
    market_sentiment: Optional[dict] = None
    sector_strength: Optional[list] = None
    institutional_flows: Optional[dict] = None
    ai_signals: Optional[dict] = None
