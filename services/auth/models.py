"""SQLAlchemy models for the Auth Service."""

from sqlalchemy import Column, String, DateTime, text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    email = Column(String, nullable=False, unique=True)
    email_hash = Column(String(64), nullable=False, unique=True)
    display_name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, server_default="USER")
    encryption_key_ref = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
