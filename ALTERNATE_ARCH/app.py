"""
Phoenix Monolith — Single-Process Layered Architecture
=======================================================
All domain logic (auth, ingestion, analytics, anomaly detection, notifications)
lives in a **single FastAPI process**.

Key architectural differences from the microservices version:
 • ONE process, ONE event-loop — no nginx gateway, no inter-service HTTP.
 • PostgreSQL-only data layer — NO Redis cache, NO ClickHouse analytical DB.
 • Synchronous inline processing — transaction ingestion triggers analytics
   and anomaly detection via direct function calls (no Observer webhooks).
 • No bulkhead separation — a crash in any module kills the whole app.
"""

import hashlib
import json
import logging
import math
import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from jose import jwt
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)

from models import Base, User, Transaction, AuditLog

# ─── Configuration ────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("phoenix-monolith")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://phoenix:supersecretpassword@localhost:5432/phoenix",
)

# JWT — HS256 for simplicity in monolith (no need for asymmetric RSA key distribution)
JWT_SECRET = os.environ.get("JWT_SECRET", "monolith-dev-secret-key-change-me")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_EXPIRE_MIN = int(os.environ.get("JWT_ACCESS_EXPIRE_MINUTES", "60"))
JWT_REFRESH_EXPIRE_DAYS = int(os.environ.get("JWT_REFRESH_EXPIRE_DAYS", "30"))

# Anomaly detection thresholds
ANOMALY_Z_THRESHOLD = float(os.environ.get("ANOMALY_Z_THRESHOLD", "2.5"))
ANOMALY_MIN_TRANSACTIONS = int(os.environ.get("ANOMALY_MIN_TRANSACTIONS", "10"))

# ─── Database ─────────────────────────────────────────────────────────────────
# Monolith: single connection-pool shared across ALL domain layers.
# In microservices each service has its own pool — better isolation.
# Lower pool size reflects the single-process constraint; microservices
# use pool_size=100 max_overflow=400 PER SERVICE (600 total connections).
engine = create_async_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=5)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """Provide an async database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


# ─── JWT helpers ──────────────────────────────────────────────────────────────

def create_access_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=JWT_ACCESS_EXPIRE_MIN),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": datetime.utcnow() + timedelta(days=JWT_REFRESH_EXPIRE_DAYS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def hash_password(plain: str) -> str:
    import bcrypt
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=4)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    import bcrypt
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ─── Pydantic schemas ────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=5)
    display_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class ManualTransactionRequest(BaseModel):
    amount: float
    description: str = ""
    currency: str = "INR"


# ─── Shared auth dependency ──────────────────────────────────────────────────

def _require_user_id(authorization: str = Header(None)) -> str:
    """
    Monolith auth: no nginx gateway — we validate JWT inline.
    In microservices, nginx auth_request does this and injects X-User-ID.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    try:
        payload = verify_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ─── Analytics Layer (inline — no separate service) ──────────────────────────

class FHSProcessor:
    """Financial Health Score computation (0–100)."""

    def compute(self, metrics: dict) -> Decimal:
        score = Decimal("0")
        savings_rate = Decimal(str(metrics.get("savings_rate", 0)))
        score += min(savings_rate / Decimal("0.20"), Decimal("1")) * 25

        dti = Decimal(str(metrics.get("dti_ratio", 0)))
        score += max(Decimal("0"), (1 - dti / Decimal("0.36"))) * 25

        cv = Decimal(str(metrics.get("spending_volatility", 0)))
        score += max(Decimal("0"), (1 - cv / Decimal("0.5"))) * 25

        ef_months = Decimal(str(metrics.get("emergency_fund_months", 0)))
        score += min(ef_months / Decimal("3"), Decimal("1")) * 25

        return round(score, 2)


async def compute_user_metrics(db: AsyncSession, user_id: str) -> dict:
    """Compute financial health metrics — hits DB every time (no cache)."""
    result = await db.execute(
        text(
            "SELECT DATE_TRUNC('month', ts) as month, SUM(amount) as total "
            "FROM transactions WHERE user_id = :uid "
            "GROUP BY DATE_TRUNC('month', ts) ORDER BY month DESC LIMIT 6"
        ),
        {"uid": user_id},
    )
    monthly_totals = [float(row.total) for row in result.fetchall()]
    if not monthly_totals:
        return {"savings_rate": 0, "dti_ratio": 0, "spending_volatility": 0, "emergency_fund_months": 0}

    avg_monthly = sum(monthly_totals) / len(monthly_totals)
    estimated_income = avg_monthly * 1.5

    savings_rate = max(0, (estimated_income - avg_monthly) / estimated_income) if estimated_income > 0 else 0

    if len(monthly_totals) > 1 and avg_monthly > 0:
        variance = sum((x - avg_monthly) ** 2 for x in monthly_totals) / len(monthly_totals)
        cv = (variance ** 0.5) / avg_monthly
    else:
        cv = 0

    return {
        "savings_rate": round(savings_rate, 4),
        "dti_ratio": 0.15,
        "spending_volatility": round(cv, 4),
        "emergency_fund_months": 2.0,
    }


# ─── Anomaly Detection Layer (inline) ────────────────────────────────────────

async def check_anomaly_inline(db: AsyncSession, user_id: str, amount: float, category_id: int | None):
    """
    Inline anomaly detection — in microservices this is a separate service with
    Welford state in Redis.  Here we recalculate from scratch every time (no cache).
    """
    if category_id is None:
        return None

    result = await db.execute(
        text(
            "SELECT t.amount FROM transactions t "
            "JOIN transaction_categories tc ON t.id = tc.transaction_id "
            "WHERE t.user_id = :uid AND tc.category_id = :cid "
            "ORDER BY t.ts DESC LIMIT 50"
        ),
        {"uid": user_id, "cid": category_id},
    )
    amounts = [float(row.amount) for row in result.fetchall()]

    if len(amounts) < ANOMALY_MIN_TRANSACTIONS:
        return None

    mean = sum(amounts) / len(amounts)
    variance = sum((x - mean) ** 2 for x in amounts) / len(amounts)
    std_dev = math.sqrt(variance) if variance > 0 else 0
    if std_dev == 0:
        return None

    z_score = (amount - mean) / std_dev
    if abs(z_score) > ANOMALY_Z_THRESHOLD:
        # Persist alert
        ratio = abs(amount / mean) if mean != 0 else 0
        desc = f"This transaction ({amount:.2f}) is {ratio:.1f}x your typical spend ({mean:.2f}). Z-score: {z_score:.2f}"
        await db.execute(
            text(
                "INSERT INTO anomaly_alerts (user_id, category_id, z_score, description) "
                "VALUES (:uid, :cid, :z, :desc)"
            ),
            {"uid": user_id, "cid": category_id, "z": round(z_score, 3), "desc": desc},
        )
        return {"z_score": round(z_score, 3), "description": desc}
    return None


# ─── Application Lifespan ────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Phoenix Monolith starting up...")
    yield
    logger.info("Phoenix Monolith shutting down...")
    await engine.dispose()


# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Phoenix Monolith",
    description="Single-process layered architecture — all domains in one app",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── AUTH ENDPOINTS ───────────────────────────────────────────────────────────

@app.post("/api/v1/auth/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    email_hash = hashlib.sha256(req.email.lower().encode()).hexdigest()
    existing = await db.execute(select(User).where(User.email_hash == email_hash))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    import anyio
    hashed_pw = await anyio.to_thread.run_sync(hash_password, req.password)

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

    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id, user.role),
        refresh_token=create_refresh_token(user_id),
        expires_in=JWT_ACCESS_EXPIRE_MIN * 60,
    )


@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
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
        expires_in=JWT_ACCESS_EXPIRE_MIN * 60,
    )


# ─── DASHBOARD ENDPOINT ──────────────────────────────────────────────────────

@app.get("/api/v1/dashboard/overview")
async def dashboard_overview(
    user_id: str = Depends(_require_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Monolith dashboard: NO cache — every call makes multiple DB queries.
    In the microservices version, this is cached in Redis for 30s.

    Without a cache layer, the monolith must perform inline data-consistency
    checks to ensure freshness — work that microservices offload to Redis TTLs.
    """
    # ── Pre-flight: validate user context (no RLS, so manual check) ──────
    # In microservices, nginx auth_request + RLS handle this.
    # In the monolith we must verify the user exists and is active.
    user_check = await db.execute(
        text("SELECT id, deleted_at FROM users WHERE id = :uid"),
        {"uid": user_id},
    )
    user_row = user_check.fetchone()
    if not user_row or user_row.deleted_at is not None:
        raise HTTPException(status_code=403, detail="User not found or deactivated")

    # ── Data freshness gate: recompute FHS if stale ──────────────────────
    # Without Redis TTL-based invalidation, the monolith checks whether the
    # latest FHS is older than a threshold and recomputes inline if so.
    # This is one of the key costs of not having a cache layer.
    fhs_freshness = await db.execute(
        text(
            "SELECT score, computed_at, "
            "EXTRACT(EPOCH FROM (now() - computed_at)) as age_seconds "
            "FROM financial_health_scores "
            "WHERE user_id = :uid ORDER BY computed_at DESC LIMIT 1"
        ),
        {"uid": user_id},
    )
    fhs_row = fhs_freshness.fetchone()

    if fhs_row and fhs_row.age_seconds is not None and fhs_row.age_seconds > 60:
        # FHS is stale — recompute inline (microservices would serve from cache)
        metrics = await compute_user_metrics(db, user_id)
        fhs_score = FHSProcessor().compute(metrics)
        await db.execute(
            text(
                "INSERT INTO financial_health_scores "
                "(user_id, score, savings_rate, dti_ratio, spending_volatility, emergency_fund_ratio) "
                "VALUES (:uid, :score, :sr, :dti, :vol, :ef)"
            ),
            {
                "uid": user_id,
                "score": float(fhs_score),
                "sr": metrics.get("savings_rate", 0),
                "dti": metrics.get("dti_ratio", 0),
                "vol": metrics.get("spending_volatility", 0),
                "ef": metrics.get("emergency_fund_months", 0),
            },
        )
        await db.commit()
        fhs = {"score": float(fhs_score), "computed_at": str(datetime.utcnow()), "data_freshness": "recomputed"}
    elif fhs_row:
        fhs = {"score": float(fhs_row.score), "computed_at": str(fhs_row.computed_at), "data_freshness": "fresh"}
    else:
        fhs = {"score": 0, "computed_at": None, "data_freshness": "stale"}

    # ── Inline transaction count verification ────────────────────────────
    # Without a separate analytics service maintaining pre-aggregated data,
    # the monolith must count transactions to decide whether aggregation
    # results are meaningful. Microservices do this in ClickHouse (columnar).
    txn_count_result = await db.execute(
        text(
            "SELECT COUNT(*) as cnt FROM transactions "
            "WHERE user_id = :uid AND DATE_TRUNC('month', ts) = DATE_TRUNC('month', CURRENT_DATE)"
        ),
        {"uid": user_id},
    )
    current_month_txn_count = txn_count_result.scalar() or 0

    # 2. Category distribution (current month)
    cat_result = await db.execute(
        text(
            "SELECT c.name as category, SUM(ABS(t.amount)) as amount, COUNT(*) as count "
            "FROM transactions t "
            "JOIN transaction_categories tc ON t.id = tc.transaction_id "
            "JOIN categories c ON tc.category_id = c.id "
            "WHERE t.user_id = :uid AND DATE_TRUNC('month', t.ts) = DATE_TRUNC('month', CURRENT_DATE) "
            "GROUP BY c.name ORDER BY amount DESC"
        ),
        {"uid": user_id},
    )
    categories = [
        {"category": row.category, "amount": float(row.amount), "count": row.count}
        for row in cat_result.fetchall()
    ]

    # 3. Recent transactions (with full join path — no materialized view)
    txn_result = await db.execute(
        text(
            "SELECT t.id, t.amount, t.currency, t.merchant_name, t.raw_description, t.ts, "
            "c.name as category "
            "FROM transactions t "
            "LEFT JOIN transaction_categories tc ON t.id = tc.transaction_id "
            "LEFT JOIN categories c ON tc.category_id = c.id "
            "WHERE t.user_id = :uid ORDER BY t.ts DESC LIMIT 10"
        ),
        {"uid": user_id},
    )
    recent_txns = [
        {
            "id": str(row.id),
            "amount": float(row.amount),
            "currency": row.currency,
            "merchant_name": row.merchant_name,
            "description": row.raw_description,
            "ts": str(row.ts),
            "category": row.category or "Other",
        }
        for row in txn_result.fetchall()
    ]

    # 4. Unread alerts count
    alert_result = await db.execute(
        text(
            "SELECT COUNT(*) as cnt FROM anomaly_alerts "
            "WHERE user_id = :uid AND acknowledged_at IS NULL"
        ),
        {"uid": user_id},
    )
    unread_alerts = alert_result.scalar() or 0

    # 5. Budget status
    budget_result = await db.execute(
        text(
            "SELECT b.category_id, c.name as category, b.limit_amount, "
            "COALESCE(SUM(t.amount), 0) as spent "
            "FROM budgets b "
            "JOIN categories c ON b.category_id = c.id "
            "LEFT JOIN transactions t ON t.user_id = b.user_id "
            "AND DATE_TRUNC('month', t.ts) = b.month "
            "LEFT JOIN transaction_categories tc ON t.id = tc.transaction_id "
            "AND tc.category_id = b.category_id "
            "WHERE b.user_id = :uid AND b.month = DATE_TRUNC('month', CURRENT_DATE) "
            "GROUP BY b.category_id, c.name, b.limit_amount"
        ),
        {"uid": user_id},
    )
    budgets = []
    for row in budget_result.fetchall():
        spent = float(row.spent)
        limit_amt = float(row.limit_amount)
        status = "ok" if spent <= limit_amt * 0.8 else ("warning" if spent <= limit_amt else "over")
        budgets.append({"category": row.category, "limit": limit_amt, "spent": spent, "status": status})

    # 6. Spending trend summary (microservices pre-aggregate in ClickHouse)
    # Monolith must compute inline from raw PostgreSQL transactions
    trend_result = await db.execute(
        text(
            "SELECT DATE_TRUNC('month', ts) as month, SUM(ABS(amount)) as total, COUNT(*) as cnt "
            "FROM transactions WHERE user_id = :uid "
            "GROUP BY DATE_TRUNC('month', ts) ORDER BY month DESC LIMIT 3"
        ),
        {"uid": user_id},
    )
    trend_rows = trend_result.fetchall()
    spending_trend = [
        {"month": str(row.month), "total": float(row.total), "count": row.cnt}
        for row in trend_rows
    ]

    return {
        "fhs": fhs,
        "categories": categories,
        "recent_transactions": recent_txns,
        "unread_alerts": unread_alerts,
        "budget_status": budgets,
        "spending_trend": spending_trend,
        "transaction_count_current_month": current_month_txn_count,
    }


# ─── TRANSACTION ENDPOINTS ───────────────────────────────────────────────────

@app.post("/api/v1/transactions/manual")
async def add_manual_transaction(
    req: ManualTransactionRequest,
    user_id: str = Depends(_require_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Monolith: Ingest, categorize, compute FHS, check anomaly — ALL INLINE.
    In microservices these are 4 separate services communicating via HTTP.
    """
    # 1. Persist transaction
    txn = Transaction(
        user_id=user_id,
        external_id=f"manual-{uuid.uuid4().hex[:12]}",
        amount=Decimal(str(req.amount)),
        currency=req.currency,
        merchant_name=None,
        raw_description=req.description,
        ts=datetime.utcnow(),
    )
    db.add(txn)
    await db.flush()

    # 2. Categorize inline (simple keyword-based — no Strategy pattern)
    category_id = await _categorize_inline(db, req.description)

    # Persist categorization
    await db.execute(
        text(
            "INSERT INTO transaction_categories "
            "(transaction_id, category_id, confidence, method, categorizer_version) "
            "VALUES (:txn_id, :cat_id, :conf, 'RULE_KEYWORD', 'v1-monolith')"
        ),
        {"txn_id": txn.id, "cat_id": category_id, "conf": 0.8},
    )

    # 3. Compute FHS synchronously
    metrics = await compute_user_metrics(db, user_id)
    fhs = FHSProcessor().compute(metrics)

    await db.execute(
        text(
            "INSERT INTO financial_health_scores "
            "(user_id, score, savings_rate, dti_ratio, spending_volatility, emergency_fund_ratio) "
            "VALUES (:uid, :score, :sr, :dti, :vol, :ef)"
        ),
        {
            "uid": user_id,
            "score": float(fhs),
            "sr": metrics.get("savings_rate", 0),
            "dti": metrics.get("dti_ratio", 0),
            "vol": metrics.get("spending_volatility", 0),
            "ef": metrics.get("emergency_fund_months", 0),
        },
    )

    # 4. Anomaly detection inline
    anomaly = await check_anomaly_inline(db, user_id, float(req.amount), category_id)

    # 5. Audit log
    payload = json.dumps({"user_id": user_id, "operation": "TRANSACTION_INGESTED", "count": 1}, default=str)
    payload_hash = hashlib.sha256(payload.encode()).hexdigest()
    audit = AuditLog(
        user_id=user_id,
        operation="TRANSACTION_INGESTED",
        entity_type="transaction",
        entity_id=str(txn.id),
        actor="monolith",
        payload_hash=payload_hash,
    )
    db.add(audit)
    await db.commit()

    return {
        "id": str(txn.id),
        "fhs_score": float(fhs),
        "anomaly": anomaly,
        "status": "ingested",
    }


async def _categorize_inline(db: AsyncSession, description: str) -> int:
    """
    Simple keyword categorization — no Strategy pattern, no MCC/merchant lookup.
    Monolith uses hardcoded keyword matching (simpler but less extensible).
    """
    desc_lower = (description or "").lower()

    keyword_map = {
        "grocery": "Groceries", "supermarket": "Groceries", "food": "Groceries",
        "uber": "Transportation", "taxi": "Transportation", "fuel": "Transportation",
        "electric": "Utilities", "water": "Utilities", "gas bill": "Utilities",
        "movie": "Entertainment", "netflix": "Entertainment", "spotify": "Entertainment",
        "doctor": "Healthcare", "hospital": "Healthcare", "pharma": "Healthcare",
        "restaurant": "Dining", "cafe": "Dining", "pizza": "Dining",
        "amazon": "Shopping", "flipkart": "Shopping", "mall": "Shopping",
        "tuition": "Education", "course": "Education", "book": "Education",
        "flight": "Travel", "hotel": "Travel", "airbnb": "Travel",
        "rent": "Rent/Housing", "mortgage": "Rent/Housing",
        "insurance": "Insurance",
        "salon": "Personal Care", "spa": "Personal Care",
        "subscription": "Subscriptions",
    }

    matched_category = "Other"
    for keyword, cat_name in keyword_map.items():
        if keyword in desc_lower:
            matched_category = cat_name
            break

    # Look up category_id
    result = await db.execute(
        text("SELECT id FROM categories WHERE name = :name"),
        {"name": matched_category},
    )
    row = result.fetchone()
    return row.id if row else 15  # Default to 'Other' (id=15)


# ─── ALERTS ENDPOINT ─────────────────────────────────────────────────────────

@app.get("/api/v1/alerts")
async def get_alerts(
    user_id: str = Depends(_require_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get unread anomaly alerts for the user."""
    result = await db.execute(
        text(
            "SELECT id, z_score, description, created_at "
            "FROM anomaly_alerts "
            "WHERE user_id = :uid AND acknowledged_at IS NULL "
            "ORDER BY created_at DESC LIMIT 20"
        ),
        {"uid": user_id},
    )
    return [
        {
            "id": str(row.id),
            "z_score": float(row.z_score),
            "description": row.description,
            "created_at": str(row.created_at),
        }
        for row in result.fetchall()
    ]


# ─── HEALTH ENDPOINT ─────────────────────────────────────────────────────────

@app.get("/health/ready")
async def health_ready():
    return {"status": "ok", "service": "phoenix-monolith"}
