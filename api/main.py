from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, Date, ForeignKey, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy import or_, func, String
from typing import Optional, List
from datetime import date
import os

from ai import categorize_with_openai

from typing import List, Optional, Dict, Any
from datetime import date, timedelta
from sqlalchemy import text
from pydantic import BaseModel
from decimal import Decimal

from advisor import ai_make_advice, find_cheaper_alt
from finance_utils import future_value_monthly_contrib



DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------- Models ----------

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, nullable=False, default=1)
    date = Column(Date, nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    merchant_raw = Column(String, nullable=True)

    enriched = relationship("EnrichedTransaction", back_populates="transaction", uselist=False)


class EnrichedTransaction(Base):
    __tablename__ = "enriched_transactions"
    __allow_unmapped__ = True  

    transaction_id = Column(Integer, ForeignKey("transactions.id"), primary_key=True)

    merchant = Column(String, nullable=True)
    category = Column(String, nullable=True)
    subcategory = Column(String, nullable=True)
    is_subscription = Column(Boolean, default=False, nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    notes = Column(String, nullable=True)

    # Unique constraint to prevent duplicate enrichments for the same transaction
    spending_class = Column(String(16), nullable=True)  # "need" | "want" | "savings"

    transaction = relationship("Transaction", back_populates="enriched")



Base.metadata.create_all(bind=engine)

# ---------- App & CORS ----------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Schemas ----------

class TxIn(BaseModel):
    account_id: int = 1
    date: str  # "YYYY-MM-DD"
    description: str = Field(..., min_length=1)
    amount: float
    merchant_raw: Optional[str] = None

class TxOut(BaseModel):
    id: int
    account_id: int
    date: date
    description: str
    amount: float
    merchant_raw: Optional[str] = None

    class Config:
        orm_mode = True

class EnrichedOut(BaseModel):
    transaction_id: int
    merchant: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    is_subscription: Optional[bool] = None
    confidence: Optional[float] = None
    notes: Optional[str] = None
    spending_class: Optional[str] = None

    class Config:
        orm_mode = True

class CategorizeIn(BaseModel):
    description: str
    amount: float
    transaction_id: Optional[int] = None

class AdviceOut(BaseModel):
    id: int
    created_at: str
    kind: str
    title: str
    body: str
    monthly_saving: Optional[float] = None
    annual_saving: Optional[float] = None
    projection_10y: Optional[float] = None
    confidence: Optional[float] = None
    tx_ids: List[int]
    meta: Dict[str, Any] = {}

# ---------- Routes ----------

from sqlalchemy import or_, func, String 

@app.get("/transactions", response_model=List[TxOut])
def list_transactions(limit: int = 100, q: Optional[str] = None):
    db = SessionLocal()
    try:
        base_query = (
            db.query(Transaction)
            .outerjoin(EnrichedTransaction, EnrichedTransaction.transaction_id == Transaction.id)
        )

        if q:
            like = f"%{q}%"
            base_query = base_query.filter(
                or_(
                    Transaction.description.ilike(like),
                    Transaction.merchant_raw.ilike(like),
                    func.cast(Transaction.amount, String).ilike(like),
                    EnrichedTransaction.merchant.ilike(like),
                    EnrichedTransaction.category.ilike(like),
                    EnrichedTransaction.subcategory.ilike(like),
                    EnrichedTransaction.notes.ilike(like),
                    EnrichedTransaction.spending_class.ilike(like),
                )
            )

        rows = (
            base_query
            .order_by(Transaction.id.desc())
            .limit(limit)
            .all()
        )
        return rows
    finally:
        db.close()

@app.post("/transactions", response_model=TxOut, status_code=201)
def create_transaction(body: TxIn):
    db = SessionLocal()
    try:
        tx = Transaction(
            account_id=body.account_id,
            date=body.date,  # Pydantic str → SQLAlchemy Date auto-coerces via DB driver
            description=body.description,
            amount=body.amount,
            merchant_raw=body.merchant_raw,
        )
        db.add(tx)
        db.commit()
        db.refresh(tx)
        return tx
    finally:
        db.close()

@app.get("/transactions/{tx_id}/enriched", response_model=Optional[EnrichedOut])
def get_enriched(tx_id: int):
    db = SessionLocal()
    try:
        row = db.query(EnrichedTransaction).filter_by(transaction_id=tx_id).first()
        if not row:
            return None
        return row
    finally:
        db.close()

@app.post("/categorize", response_model=EnrichedOut)
def categorize(body: CategorizeIn):
    """
    Always return a JSON enrichment object.
    Never raise 5xx if OpenAI is down or rate-limited — ai.categorize_with_openai already
    returns a safe fallback payload in those cases.
    """
    # 1) Get enrichment (this never throws fatal errors; it returns a stub on failure)
    result = categorize_with_openai(body.description, body.amount)

    # 2) If there is no transaction_id, just echo the result (used for preview flows)
    if not body.transaction_id:
        return EnrichedOut(
            transaction_id=0,
            merchant=result.get("merchant"),
            category=result.get("category"),
            subcategory=result.get("subcategory"),
            is_subscription=bool(result.get("is_subscription", False)),
            confidence=float(result.get("confidence", 0.0)),
            notes=result.get("notes"),
            spending_class=result.get("spending_class"),
        )

    # 3) Persist enrichment to the DB for the given transaction
    db = SessionLocal()
    try:
        tx = db.query(Transaction).filter_by(id=body.transaction_id).first()
        if not tx:
            # 404 for unknown transaction id
            raise HTTPException(status_code=404, detail=f"Transaction {body.transaction_id} not found")

        row = db.query(EnrichedTransaction).filter_by(transaction_id=tx.id).first()
        if not row:
            row = EnrichedTransaction(transaction_id=tx.id)
            db.add(row)

        row.merchant = result.get("merchant")
        row.category = result.get("category")
        row.subcategory = result.get("subcategory")
        row.is_subscription = bool(result.get("is_subscription", False))
        row.confidence = float(result.get("confidence", 0.0))
        row.notes = result.get("notes")
        row.spending_class = result.get("spending_class")

        db.commit()
        db.refresh(row)

        # Return exactly what the frontend expects
        return EnrichedOut(
            transaction_id=tx.id,
            merchant=row.merchant,
            category=row.category,
            subcategory=row.subcategory,
            is_subscription=row.is_subscription,
            confidence=row.confidence,
            notes=row.notes,
            spending_class=row.spending_class,
        )
    finally:
        db.close()

@app.post("/advisor/run_subscriptions")
def advisor_run_subscriptions(days: int = 120, region: str = "IE", min_diff: float = 1.0):
    db = SessionLocal()
    created = 0
    try:
        since = date.today() - timedelta(days=days)
        rows = (
            db.query(Transaction, EnrichedTransaction)
            .outerjoin(EnrichedTransaction, EnrichedTransaction.transaction_id == Transaction.id)
            .filter(Transaction.date >= since)
            .order_by(Transaction.date.desc())
            .all()
        )
        seen_keys = set()

        for t, e in rows:
            # subscription-like?
            is_sub = bool(e and e.is_subscription) or "subscription" in (e.category or "").lower()
            if not is_sub:
                continue

            key = (e.merchant or t.merchant_raw or t.description or "").lower()
            if key in seen_keys:
                continue
            seen_keys.add(key)

            alt = get_benchmark_alt(db, key, region=region)
            if not alt:
                continue

            diff = alt["current"]["price"] - alt["alternative"]["price"]
            if diff < min_diff:
                continue

            ms = round(diff, 2)
            an = round(diff * 12, 2)
            p10 = round(future_value_monthly_contrib(ms, 0.07, 10), 2)

            title = f"Consider switching from {alt['current']['provider']} to {alt['alternative']['provider']}"
            body = (
                f"Current: {alt['current']['provider']} {alt['current']['plan'] or ''} at "
                f"€{alt['current']['price']:.2f}/mo. "
                f"Alternative: {alt['alternative']['provider']} {alt['alternative']['plan'] or ''} at "
                f"€{alt['alternative']['price']:.2f}/mo. "
                f"Save ≈ €{ms:.2f}/mo (≈ €{an:.2f}/yr). "
                f"If invested at 7% annual return, 10y could grow to ≈ €{p10:.2f}."
            )

            db.execute(text("""
                INSERT INTO advice_insights
                (tx_ids, kind, title, body, monthly_saving, annual_saving, projection_10y, confidence, meta)
                VALUES (:tx_ids, :kind, :title, :body, :ms, :as, :p10, :conf, :meta)
            """), {
                "tx_ids": [t.id],
                "kind": "switch",
                "title": title,
                "body": body,
                "ms": ms, "as": an, "p10": p10,
                "conf": 0.8,
                "meta": json.dumps({"merchant_key": key, "region": region})
            })
            created += 1

        db.commit()
        return {"created": created}
    finally:
        db.close()

@app.post("/advisor/run_wants")
def advisor_run_wants(days: int = 90, region: str = "IE", cut_percent: float = 0.5, expected_return: float = 0.07, years: int = 10):
    """
    Find consistent 'want' spending patterns, suggest a DIY recipe to keep the want cheaper,
    and project the value if the cut portion were invested.
    """
    db = SessionLocal()
    created = 0
    try:
        since = date.today() - timedelta(days=days)
        pairs = (
            db.query(Transaction, EnrichedTransaction)
            .outerjoin(EnrichedTransaction, EnrichedTransaction.transaction_id == Transaction.id)
            .filter(Transaction.date >= since)
            .order_by(Transaction.date.desc())
            .all()
        )

        groups: Dict[str, Dict[str, Any]] = {}
        for t, e in pairs:
            # only wants
            if not e or (e.spending_class or "").lower() != "want":
                continue
            k = normalize_key(t.description, t.merchant_raw, e.merchant)
            g = groups.setdefault(k, {"tx_ids": [], "total": 0.0, "sample_desc": t.description, "brand": e.merchant or t.merchant_raw})
            g["tx_ids"].append(t.id)
            g["total"] += float(t.amount)

        for k, g in groups.items():
            # require some frequency
            if len(g["tx_ids"]) < 4:
                continue

            est_monthly = round(estimate_monthly_from_window(g["total"], days), 2)
            if est_monthly <= 0.0:
                continue

            # invest-the-difference if cutting by cut_percent
            cut_monthly = round(est_monthly * float(cut_percent), 2)
            proj = round(future_value_monthly_contrib(cut_monthly, expected_return, years), 2)

            # try to pick a homebrew item label from the description/merchant
            desc = g["sample_desc"].lower()
            item_label = "coffee" if any(x in desc for x in ["coffee","latte","cappuccino","americano","starbucks","cafe"]) else "burger" if "burger" in desc else "treat"
            home_cost = get_homebrew_cost(db, item_label, region=region) or 1.0

            recipe = suggest_recipe_for(item_label, brand_hint=g["brand"])

            title = f"Cut {int(cut_percent*100)}% of your '{k}' spend and invest the rest"
            body = (
                f"You spend ≈ €{est_monthly:.2f}/mo on this want. "
                f"Cutting {int(cut_percent*100)}% frees ≈ €{cut_monthly:.2f}/mo; "
                f"invested at {int(expected_return*100)}% for {years}y → ≈ €{proj:.2f}.\n\n"
                f"Keep the treat: try this at-home recipe — {recipe.get('title')} "
                f"(~€{recipe.get('est_cost_per_serving', home_cost):.2f}/serving, ~{int(recipe.get('time_minutes',5))} min)."
            )

            db.execute(text("""
                INSERT INTO advice_insights
                (tx_ids, kind, title, body, monthly_saving, annual_saving, projection_10y, confidence, meta)
                VALUES (:tx_ids, :kind, :title, :body, :ms, :as, :p10, :conf, :meta)
            """), {
                "tx_ids": g["tx_ids"][:20],  # cap list length per card
                "kind": "cutback",
                "title": title,
                "body": body,
                "ms": cut_monthly,
                "as": round(cut_monthly * 12, 2),
                "p10": proj,
                "conf": 0.75,
                "meta": json.dumps({
                    "merchant_key": k,
                    "item": item_label,
                    "recipe": recipe
                })
            })
            created += 1

        db.commit()
        return {"created": created}
    finally:
        db.close()


@app.get("/advisor/{transaction_id}")
def get_advice(transaction_id: int):
    """
    Return AI-generated advice for a single transaction.
    """
    db = SessionLocal()
    try:
        tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found")

        # Call the advisor AI function (handles merchant, amount, description)
        advice = ai_make_advice({
            "id": tx.id,
            "description": tx.description,
            "amount": tx.amount,
            "merchant": tx.merchant_raw,
        })

        return {
            "transaction_id": tx.id,
            "advice": advice,
        }
    finally:
        db.close()

@app.post("/advice/run")
def run_advice(days: int = 90):
    db = SessionLocal()
    try:
        since = date.today() - timedelta(days=days)
        # Pull base rows + enrichment since date
        rows = (
            db.query(Transaction, EnrichedTransaction)
            .outerjoin(EnrichedTransaction, EnrichedTransaction.transaction_id == Transaction.id)
            .filter(Transaction.date >= since)
            .order_by(Transaction.date.desc())
            .all()
        )

        # Group by coarse merchant/desc
        groups: Dict[str, Dict[str, Any]] = {}

        def key_for(t: Transaction, e: Optional[EnrichedTransaction]):
            base = (e.merchant or t.merchant_raw or t.description or "").strip().lower()
            return base or f"id-{t.id}"

        for (t, e) in rows:
            k = key_for(t, e)
            g = groups.setdefault(k, {"txs": [], "merchant_hint": k})
            g["txs"].append({"id": t.id, "amount": t.amount, "desc": t.description, "enriched": e})

        # evaluate groups
        created = 0
        for k, g in groups.items():
            txs = g["txs"]
            ids = [t["id"] for t in txs]
            amounts = [Decimal(str(t["amount"])) for t in txs]
            first_e = txs[0]["enriched"] if txs else None
            desc_sample = txs[0]["desc"] if txs else ""

            # heuristics
            dup, anomaly = is_dup_or_anomaly_group(amounts)
            sub_like = is_subscription_like(first_e)
            high_freq = is_high_frequency_merchant([r for r in rows if r[0].id in ids])
            coffeeish = is_daily_coffee_pattern(desc_sample, first_e)

            numeric: Dict[str, Any] = {"merchant": g["merchant_hint"], "tx_ids": ids, "facts": {}}

            # Duplicates/anomalies
            if dup:
                numeric["facts"]["duplicate"] = True
            if anomaly:
                numeric["facts"]["anomaly"] = True

            # Subscription or phone/internet provider switch
            if sub_like or any(x in k for x in ("vodafone","eir","three ie","netflix","spotify","prime")):
                alt = find_cheaper_alt(db, k, region="IE")
                if alt:
                    diff = max(0.0, alt["current"]["price"] - alt["alternative"]["price"])
                    if diff >= 1.0:  # only mention if >= €1/mo
                        numeric["facts"]["switch"] = {
                            "current": alt["current"],
                            "alternative": alt["alternative"],
                            "monthly_saving": round(diff, 2),
                            "annual_saving": round(diff * 12, 2),
                            "projection_10y": round(future_value_monthly_contrib(diff, 0.07, 10), 2),
                        }

            # Habit: coffee/fast food high frequency → cutback + invest-the-difference
            if coffeeish or high_freq:
                avg_spend = float(sum(amounts)) / max(1, len(amounts))
                # estimate monthly spend if habit is weekly 5x (approx from high_freq)
                # simpler: use last 30 days in this group
                monthly_spend = float(sum(a for a in amounts))  # already last 90 days; we’ll rough it
                est_monthly = round(monthly_spend / 3.0, 2) if days >= 90 else round(monthly_spend, 2)
                proj10 = round(future_value_monthly_contrib(est_monthly, 0.07, 10), 2)
                numeric["facts"]["habit"] = {
                    "estimated_monthly": est_monthly,
                    "estimated_annual": round(est_monthly * 12, 2),
                    "invest_projection_10y": proj10,
                    "recipe_suggestion_ok": True if coffeeish else False
                }

            # If no facts, skip group
            if not numeric["facts"]:
                continue

            # Ask AI to turn facts into concise cards
            try:
                advice_items = ai_make_advice(numeric)
            except Exception:
                advice_items = []

            # Persist items
            for item in advice_items:
                db.execute(text("""
                    INSERT INTO advice_insights
                    (tx_ids, kind, title, body, monthly_saving, annual_saving, projection_10y, confidence, meta)
                    VALUES (:tx_ids, :kind, :title, :body, :ms, :as, :p10, :conf, :meta)
                """), {
                    "tx_ids": ids,
                    "kind": item.get("kind"),
                    "title": item.get("title",""),
                    "body": item.get("body",""),
                    "ms": item.get("monthly_saving"),
                    "as": item.get("annual_saving"),
                    "p10": item.get("projection_10y"),
                    "conf": item.get("confidence", 0.7),
                    "meta": json.dumps({"tags": item.get("tags", []), "merchant": k, "facts": numeric["facts"]})
                })
                created += 1

        db.commit()
        return {"created": created}
    finally:
        db.close()

@app.get("/advice/latest", response_model=List[AdviceOut])
def advice_latest(limit: int = 20):
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT id, created_at, kind, title, body, monthly_saving, annual_saving, projection_10y, confidence, tx_ids, meta
            FROM advice_insights
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"limit": limit}).fetchall()

        res: List[AdviceOut] = []
        for r in rows:
            res.append(AdviceOut(
                id=r[0],
                created_at=r[1].isoformat(),
                kind=r[2],
                title=r[3],
                body=r[4],
                monthly_saving=float(r[5]) if r[5] is not None else None,
                annual_saving=float(r[6]) if r[6] is not None else None,
                projection_10y=float(r[7]) if r[7] is not None else None,
                confidence=float(r[8]) if r[8] is not None else None,
                tx_ids=list(r[9]),
                meta=r[10] or {},
            ))
        return res
    finally:
        db.close()