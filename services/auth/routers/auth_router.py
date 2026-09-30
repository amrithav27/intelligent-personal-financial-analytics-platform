"""Auth Service — Router with registration, login, refresh, token validation, profile, and settings endpoints."""

import hashlib
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (
    create_access_token,
    create_refresh_token,
    verify_token,
    hash_password,
    verify_password,
    ACCESS_EXPIRE_MIN,
)
from models import User
from schemas import (
    RegisterRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
    UpdateProfileRequest,
    ChangePasswordRequest,
    NotificationPrefItem,
    NotificationPrefsUpdateRequest,
    NotificationPrefResponse,
    HealthResponse,
)

router = APIRouter()


async def get_db():
    """Dependency — injected by main.py."""
    raise NotImplementedError("get_db must be overridden at app startup")


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    # Check if user already exists
    email_hash = hashlib.sha256(req.email.lower().encode()).hexdigest()
    existing = await db.execute(select(User).where(User.email_hash == email_hash))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    import anyio
    hashed_pw = await anyio.to_thread.run_sync(hash_password, req.password)

    # Create user
    user = User(
        email=req.email,
        email_hash=email_hash,
        display_name=req.display_name,
        password_hash=hashed_pw,
        role="USER",
        encryption_key_ref=f"key-{uuid.uuid4().hex[:12]}",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Issue tokens
    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id, user.role),
        refresh_token=create_refresh_token(user_id),
        expires_in=ACCESS_EXPIRE_MIN * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user and issue JWT tokens."""
    email_hash = hashlib.sha256(req.email.lower().encode()).hexdigest()
    result = await db.execute(select(User).where(User.email_hash == email_hash))
    user = result.scalar_one_or_none()

    import anyio

    if not user or not await anyio.to_thread.run_sync(verify_password, req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.deleted_at:
        raise HTTPException(status_code=403, detail="Account has been deactivated")

    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id, user.role),
        refresh_token=create_refresh_token(user_id),
        expires_in=ACCESS_EXPIRE_MIN * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Issue a new access token using a valid refresh token."""
    try:
        payload = verify_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user_id = payload["sub"]
    user_id_uuid = uuid.UUID(user_id)
    result = await db.execute(select(User).where(User.id == user_id_uuid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(user_id, user.role),
        refresh_token=create_refresh_token(user_id),
        expires_in=ACCESS_EXPIRE_MIN * 60,
    )


@router.get("/internal/validate-token")
async def validate_token(authorization: str = Header(None)):
    """
    Called by nginx auth_request to validate JWT tokens.
    Returns 200 with X-User-ID header on success, 401 on failure.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.split(" ", 1)[1]
    try:
        payload = verify_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    from fastapi.responses import Response
    response = Response(status_code=200)
    response.headers["X-User-ID"] = payload["sub"]
    response.headers["X-User-Role"] = payload.get("role", "USER")
    return response


@router.get("/health/ready", response_model=HealthResponse)
async def health_ready():
    """Health check endpoint for Docker/K8s."""
    return HealthResponse(status="ok", service="auth", timestamp=datetime.utcnow())


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    x_user_id: str = Header(None, alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Get current user profile (X-User-ID injected by gateway)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID not provided")
    user_id_uuid = uuid.UUID(x_user_id)
    result = await db.execute(select(User).where(User.id == user_id_uuid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        created_at=user.created_at,
    )


@router.put("/me", response_model=UserResponse)
async def update_profile(
    req: UpdateProfileRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's profile (display name and/or email)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID not provided")

    user_id_uuid = uuid.UUID(x_user_id)
    result = await db.execute(select(User).where(User.id == user_id_uuid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if req.display_name is not None:
        user.display_name = req.display_name

    if req.email is not None:
        new_email_hash = hashlib.sha256(req.email.lower().encode()).hexdigest()
        # Check uniqueness only if email actually changed
        if new_email_hash != user.email_hash:
            conflict = await db.execute(select(User).where(User.email_hash == new_email_hash))
            if conflict.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Email already in use by another account")
            user.email = req.email
            user.email_hash = new_email_hash

    user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)

    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        created_at=user.created_at,
    )


@router.post("/me/change-password")
async def change_password(
    req: ChangePasswordRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password (requires current password verification)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID not provided")

    user_id_uuid = uuid.UUID(x_user_id)
    result = await db.execute(select(User).where(User.id == user_id_uuid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify current password
    if not verify_password(req.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    # Hash and save new password
    user.password_hash = hash_password(req.new_password)
    user.updated_at = datetime.utcnow()
    await db.commit()

    return {"status": "ok", "message": "Password changed successfully"}


@router.get("/me/notification-preferences", response_model=list[NotificationPrefResponse])
async def get_notification_preferences(
    x_user_id: str = Header(None, alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get notification preferences for all categories.
    Returns defaults (all enabled) for categories without explicit preferences.
    """
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID not provided")

    # Get all categories with user's preferences (LEFT JOIN)
    result = await db.execute(
        text(
            "SELECT c.id AS category_id, c.name AS category_name, c.icon AS category_icon, "
            "COALESCE(np.email_enabled, true) AS email_enabled, "
            "COALESCE(np.push_enabled, true) AS push_enabled, "
            "COALESCE(np.websocket_enabled, true) AS websocket_enabled "
            "FROM categories c "
            "LEFT JOIN notification_preferences np ON c.id = np.category_id AND np.user_id = :uid "
            "ORDER BY c.id"
        ),
        {"uid": x_user_id},
    )
    return [
        NotificationPrefResponse(
            category_id=row.category_id,
            category_name=row.category_name,
            category_icon=row.category_icon,
            email_enabled=row.email_enabled,
            push_enabled=row.push_enabled,
            websocket_enabled=row.websocket_enabled,
        )
        for row in result.fetchall()
    ]


@router.put("/me/notification-preferences")
async def update_notification_preferences(
    req: NotificationPrefsUpdateRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Bulk update notification preferences per category (upsert)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID not provided")

    for pref in req.preferences:
        await db.execute(
            text(
                "INSERT INTO notification_preferences "
                "(user_id, category_id, email_enabled, push_enabled, websocket_enabled, updated_at) "
                "VALUES (:uid, :cid, :email, :push, :ws, CURRENT_TIMESTAMP) "
                "ON CONFLICT (user_id, category_id) DO UPDATE SET "
                "email_enabled = :email, push_enabled = :push, websocket_enabled = :ws, updated_at = CURRENT_TIMESTAMP"
            ),
            {
                "uid": x_user_id,
                "cid": pref.category_id,
                "email": pref.email_enabled,
                "push": pref.push_enabled,
                "ws": pref.websocket_enabled,
            },
        )
    await db.commit()
    return {"status": "ok", "updated": len(req.preferences)}
