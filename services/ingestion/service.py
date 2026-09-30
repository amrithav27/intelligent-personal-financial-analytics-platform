"""IngestionService — orchestrates adapter validation, transformation, persistence, and notification."""

import hashlib
import json
import logging
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.registry import AdapterRegistry
from adapters.base import UnifiedTransaction
from publishers.base import INotificationPublisher
from models import Transaction, AuditLog

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, db: AsyncSession, publisher: INotificationPublisher):
        self.db = db
        self.publisher = publisher

    async def ingest(self, user_id: str, source_type: str, raw_data) -> dict:
        """
        Main ingestion pipeline:
        1. Get adapter (Adapter pattern)
        2. Validate raw data
        3. Transform to UnifiedTransaction
        4. Persist to PostgreSQL (dedup by external_id)
        5. Write audit log
        6. Notify downstream (Observer pattern)
        """
        # 1. Get the right adapter
        adapter = AdapterRegistry.get(source_type)

        # 2. Validate
        result = adapter.validate(raw_data)
        if not result.is_valid:
            raise ValueError(f"Validation failed: {result.errors}")

        # 3. Transform to unified schema
        unified_txns = adapter.transform(raw_data)
        if not isinstance(unified_txns, list):
            unified_txns = [unified_txns]

        # 4. Persist to PostgreSQL (dedup by external_id)
        persisted = []
        for txn in unified_txns:
            existing = await self._find_by_external_id(user_id, txn.external_id)
            if existing:
                continue  # idempotent: skip duplicates
            db_txn = await self._save_transaction(user_id, txn)
            persisted.append(db_txn)

        # 5. Write audit log
        await self._write_audit(user_id, "TRANSACTION_INGESTED", len(persisted), raw_data)

        # 6. Notify Analytics Engine (Observer pattern)
        if persisted:
            await self.publisher.publish(
                {
                    "event": "transactions_ingested",
                    "user_id": user_id,
                    "transaction_ids": [str(t.id) for t in persisted],
                    "count": len(persisted),
                }
            )

        return {"ingested": len(persisted), "skipped": len(unified_txns) - len(persisted)}

    async def _find_by_external_id(self, user_id: str, external_id: str):
        """Check if a transaction with this external_id already exists for this user."""
        result = await self.db.execute(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def _save_transaction(self, user_id: str, txn: UnifiedTransaction) -> Transaction:
        """Persist a UnifiedTransaction to the database."""
        db_txn = Transaction(
            user_id=user_id,
            external_id=txn.external_id,
            amount=txn.amount,
            currency=txn.currency,
            merchant_name=txn.merchant_name,
            raw_description=txn.raw_description,
            mcc_code=txn.mcc_code,
            ts=txn.ts,
        )
        self.db.add(db_txn)
        await self.db.flush()
        return db_txn

    async def _write_audit(self, user_id, operation, count, raw_data):
        """Write an immutable audit log entry."""
        payload = json.dumps(
            {"user_id": user_id, "operation": operation, "count": count},
            default=str,
        )
        payload_hash = hashlib.sha256(payload.encode()).hexdigest()
        audit = AuditLog(
            user_id=user_id,
            operation=operation,
            entity_type="transaction",
            actor="ingestion-service",
            payload_hash=payload_hash,
        )
        self.db.add(audit)
        await self.db.commit()
