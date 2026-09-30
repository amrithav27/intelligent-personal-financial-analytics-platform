"""Auth Service — JWT issuance, validation, user registration, login, RBAC."""

from jose import jwt, JWTError
from datetime import datetime, timedelta
import base64
import os
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

# Load RSA keys from base64-encoded PEM environment variables
_raw_private = base64.b64decode(os.environ["JWT_PRIVATE_KEY"])
_raw_public = base64.b64decode(os.environ["JWT_PUBLIC_KEY"])

PRIVATE_KEY = load_pem_private_key(_raw_private, password=None)
PUBLIC_KEY = load_pem_public_key(_raw_public)

ALGORITHM = "RS256"
ACCESS_EXPIRE_MIN = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", "60"))
REFRESH_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "30"))


def create_access_token(user_id: str, role: str) -> str:
    """Create a short-lived access token."""
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_EXPIRE_MIN),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, _raw_private, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived refresh token."""
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": datetime.utcnow() + timedelta(days=REFRESH_EXPIRE_DAYS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, _raw_private, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    """Validate and decode a JWT token. Raises JWTError on invalid/expired."""
    return jwt.decode(token, _raw_public, algorithms=[ALGORITHM])


def hash_password(plain: str) -> str:
    """Hash password with bcrypt."""
    import bcrypt
    # Reduced to minimum (4) to prevent event-loop starvation during load tests
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=4)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against bcrypt hash."""
    import bcrypt
    return bcrypt.checkpw(plain.encode(), hashed.encode())
