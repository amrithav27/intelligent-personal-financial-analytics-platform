"""SQLAlchemy models for the Ingestion Service."""

from sqlalchemy import Column, String, DateTime, Numeric, text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


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


class TransactionSource(Base):
    __tablename__ = "transaction_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(UUID(as_uuid=True), nullable=False)
    source_type = Column(String, nullable=False)
    adapter_id = Column(String, nullable=False)
    label = Column(String, nullable=False)
    config = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


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
