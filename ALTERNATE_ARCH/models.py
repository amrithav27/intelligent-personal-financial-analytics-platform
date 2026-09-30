"""Monolith — Unified SQLAlchemy models (all tables in one file).

In a monolithic layered architecture, all domain entities live in a single
models module.  There is no per-service isolation of the data layer.
"""

from sqlalchemy import (
    Column, String, DateTime, Numeric, Integer, Boolean, Text,
    ForeignKey, text, func, CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ── Users ─────────────────────────────────────────────────────────────────
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


# ── Transactions ──────────────────────────────────────────────────────────
class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=True)
    external_id = Column(String, nullable=True)
    amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(3), nullable=False, server_default="INR")
    merchant_name = Column(String, nullable=True)
    raw_description = Column(String, nullable=True)
    mcc_code = Column(String(4), nullable=True)
    ts = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


# ── Audit Log ─────────────────────────────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), nullable=True)
    operation = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=True)
    actor = Column(String, nullable=False)
    ts = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    payload_hash = Column(String(64), nullable=False)
