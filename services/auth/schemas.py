"""Pydantic schemas for the Auth Service."""

from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=5)
    display_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[str] = Field(None, min_length=5)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class NotificationPrefItem(BaseModel):
    category_id: int
    email_enabled: bool = True
    push_enabled: bool = True
    websocket_enabled: bool = True


class NotificationPrefsUpdateRequest(BaseModel):
    preferences: list[NotificationPrefItem]


class NotificationPrefResponse(BaseModel):
    category_id: int
    category_name: str
    category_icon: Optional[str] = None
    email_enabled: bool
    push_enabled: bool
    websocket_enabled: bool


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "auth"
    timestamp: Optional[datetime] = None
