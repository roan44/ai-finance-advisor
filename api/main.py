# ---------- IMPORTS ----------
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, Date, ForeignKey, 
    UniqueConstraint, DateTime, Text, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy import or_, func, String, text
from typing import Optional, List, Dict, Any
from datetime import date, datetime, timedelta
import os
import json

from ai import categorize_with_openai
from advisor import (
    ai_make_advice, find_cheaper_alt, normalize_key, 
    estimate_monthly_from_window, get_benchmark_alt, 
    get_homebrew_cost, suggest_recipe_for
)
from finance_utils import future_value_monthly_contrib

# ---------- DATABASE SETUP ----------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://app:app@db:5432/finance")
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------- MODELS ----------
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

    transaction_id = Column(Integer, ForeignKey("transactions.id"), primary_key=True)
    merchant = Column(String, nullable=True)
    category = Column(String, nullable=True)
    subcategory = Column(String, nullable=True)
    is_subscription = Column(Boolean, default=False, nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    notes = Column(String, nullable=True)
    spending_class = Column(String(16), nullable=True)  # "need" | "want" | "savings"

    transaction = relationship("Transaction", back_populates="enriched")

class AdviceInsight(Base):
    __tablename__ = "advice_insights"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    kind = Column(String(50), nullable=False)  # "switch", "cutback", "duplicate", etc.
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    monthly_saving = Column(Float, nullable=True)
    annual_saving = Column(Float, nullable=True)
    projection_10y = Column(Float, nullable=True)
    confidence = Column(Float, default=0.7, nullable=False)
    tx_ids = Column(JSON, nullable=False)  # List of transaction IDs
    meta = Column(JSON, nullable=True)  # Additional metadata

class ProviderBenchmark(Base):
    __tablename__ = "provider_benchmarks"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(100), nullable=False)
    plan = Column(String(100), nullable=True)
    monthly_price = Column(Float, nullable=False)
    currency = Column(String(10), default="EUR", nullable=False)
    region = Column(String(10), default="IE", nullable=False)
    category = Column(String(50), nullable=True)  # "telecom", "streaming", etc.

class HomebrewCost(Base):
    __tablename__ = "homebrew_costs"

    id = Column(Integer, primary_key=True, index=True)
    item = Column(String(100), nullable=False)
    estimated_unit_cost = Column(Float, nullable=False)
    region = Column(String(10), default="IE", nullable=False)
    currency = Column(String(10), default="EUR", nullable=False)

    __table_args__ = (UniqueConstraint('item', 'region', name='unique_item_region'),)

# Create all tables
Base.metadata.create_all(bind=engine)

print("AI Finance Advisor API starting up...")
print("Database tables created successfully")
print(f"API available at: http://localhost:8000")
print(f"Docs available at: http://localhost:8000/docs")

# ---------- APP SETUP ----------
app = FastAPI(title="AI Finance Advisor", version="1.0.0")

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

# ---------- SCHEMAS ----------
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

# ---------- HELPER FUNCTIONS ----------
def is_subscription_like(enriched: Optional[EnrichedTransaction]) -> bool:
    """Check if transaction appears to be subscription-related"""
    if not enriched:
        return False
    return bool(enriched.is_subscription) or "subscription" in (enriched.category or "").lower()

def is_high_frequency_merchant(transactions: List[tuple]) -> bool:
    """Check if merchant has high frequency transactions"""
    return len(transactions) >= 4

def is_frequent_want_pattern(description: str, enriched: Optional[EnrichedTransaction]) -> bool:
    """Check if transaction is a frequent 'want' purchase that could potentially be made at home"""
    if not enriched or enriched.spending_class != "want":
        return False
    return True

def detect_item_type(description: str, merchant_hint: str = "") -> str:
    """Extract the general item/service type from transaction description for recipe suggestions"""
    full_context = f"{description} {merchant_hint}".strip()
    return full_context

def is_dup_or_anomaly_group(amounts: List[float]) -> tuple[bool, bool]:
    """Detect duplicate transactions or spending anomalies"""
    if len(amounts) < 2:
        return False, False
    
    unique_amounts = set(amounts)
    is_duplicate = len(unique_amounts) < len(amounts)
    
    avg_amount = sum(amounts) / len(amounts)
    is_anomaly = any(abs(amount - avg_amount) > avg_amount * 0.5 for amount in amounts)
    
    return is_duplicate, is_anomaly

# ---------- ROUTES ----------
@app.get("/", summary="Health Check")
def root():
    return {"message": "AI Finance Advisor API", "status": "healthy"}

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
            date=body.date,
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
    result = categorize_with_openai(body.description, body.amount)

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

    db = SessionLocal()
    try:
        tx = db.query(Transaction).filter_by(id=body.transaction_id).first()
        if not tx:
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

@app.get("/advisor/{transaction_id}")
def get_single_advice(transaction_id: int):
    """
    Return AI-generated advice for a single transaction.
    """
    db = SessionLocal()
    try:
        tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found")

        enriched = db.query(EnrichedTransaction).filter_by(transaction_id=tx.id).first()
        merchant = enriched.merchant if enriched else tx.merchant_raw

        advice = ai_make_advice(tx.description, tx.amount, merchant)

        return {
            "transaction_id": tx.id,
            "advice": advice,
        }
    finally:
        db.close()

@app.post("/advice/run")
def run_advice_analysis(days: int = 90):
    """
    Analyze recent transactions and generate financial advice insights.
    """
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

        groups: Dict[str, Dict[str, Any]] = {}
        
        for t, e in rows:
            key = normalize_key(t.description, t.merchant_raw, e.merchant if e else None)
            if key not in groups:
                groups[key] = {
                    "transactions": [],
                    "total_amount": 0.0,
                    "sample_transaction": t,
                    "sample_enrichment": e
                }
            groups[key]["transactions"].append(t)
            groups[key]["total_amount"] += abs(float(t.amount))

        for key, group in groups.items():
            txs = group["transactions"]
            sample_tx = group["sample_transaction"]
            sample_enriched = group["sample_enrichment"]
            
            # Skip if no enrichment data
            if not sample_enriched:
                continue

            est_monthly = estimate_monthly_from_window(group["total_amount"], days)
            tx_ids = [t.id for t in txs]
            
            # SUBSCRIPTION EVALUATION
            if sample_enriched.is_subscription:
                monthly_cost = est_monthly if len(txs) > 1 else abs(float(sample_tx.amount))
                
                # Try to find cheaper alternatives
                alternative = find_cheaper_alt(key, monthly_cost)
                
                # Generate subscription comparison advice
                if alternative and "no known cheaper alternatives" not in alternative.lower():
                    title = f"Switch from {sample_enriched.merchant or key} to save money"
                    body = f"Current service: {sample_enriched.merchant or key} at €{monthly_cost:.2f}/month.\n\n{alternative}"
                    
                    # Extract potential savings from AI response (rough estimate)
                    potential_savings = monthly_cost * 0.2 
                    
                    insight = AdviceInsight(
                        kind="switch",
                        title=title,
                        body=body,
                        monthly_saving=potential_savings,
                        annual_saving=potential_savings * 12,
                        projection_10y=future_value_monthly_contrib(potential_savings, 0.07, 10),
                        confidence=0.75,
                        tx_ids=tx_ids[:5],
                        meta={
                            "merchant_key": key, 
                            "analysis_type": "subscription_comparison",
                            "current_cost": monthly_cost,
                            "service_type": sample_enriched.category or "subscription"
                        }
                    )
                    db.add(insight)
                    created += 1
                else:
                    title = f"Monitor {sample_enriched.merchant or key} subscription costs"
                    body = f"You pay €{monthly_cost:.2f}/month for {sample_enriched.merchant or key}. While no cheaper alternatives were found, consider reviewing this subscription periodically for better deals."
                    
                    insight = AdviceInsight(
                        kind="monitor",
                        title=title,
                        body=body,
                        monthly_saving=None,
                        annual_saving=None,
                        projection_10y=None,
                        confidence=0.5,
                        tx_ids=tx_ids[:5],
                        meta={
                            "merchant_key": key, 
                            "analysis_type": "subscription_monitor",
                            "current_cost": monthly_cost,
                            "service_type": sample_enriched.category or "subscription"
                        }
                    )
                    db.add(insight)
                    created += 1
            
            # FREQUENT WANT SPENDING
            elif sample_enriched.spending_class == "want" and len(txs) >= 3:
                if est_monthly < 5.0:
                    continue
                    
                cut_amount = est_monthly * 0.3
                projection = future_value_monthly_contrib(cut_amount, 0.07, 10)
                
                # Get recipe suggestion for this item
                merchant_name = sample_enriched.merchant or sample_tx.merchant_raw or key
                item_context = f"{sample_tx.description} from {merchant_name}"
                recipe = suggest_recipe_for(item_context, merchant_name)
                
                # Build advice with recipe if viable
                if recipe.get('is_viable', True):
                    recipe_text = f"\n\nTry making it at home:\n"
                    recipe_text += f"Recipe: {recipe['title']}\n"
                    recipe_text += f"Time: {recipe['time_minutes']} minutes\n"
                    recipe_text += f"Cost per serving: €{recipe['est_cost_per_serving']:.2f}\n"
                    recipe_text += f"Method: {', '.join(recipe['method'][:2])}..."
                    
                    body_text = f"You spend €{est_monthly:.2f}/month on {key}. Cutting 30% (€{cut_amount:.2f}/month) and investing at 7% could grow to €{projection:.2f} in 10 years.{recipe_text}"
                else:
                    body_text = f"You spend €{est_monthly:.2f}/month on {key}. Cutting 30% (€{cut_amount:.2f}/month) and investing at 7% could grow to €{projection:.2f} in 10 years."
                
                title = f"Reduce spending on {key}"
                
                insight = AdviceInsight(
                    kind="cutback",
                    title=title,
                    body=body_text,
                    monthly_saving=cut_amount,
                    annual_saving=cut_amount * 12,
                    projection_10y=projection,
                    confidence=0.6,
                    tx_ids=tx_ids[:10],
                    meta={"merchant_key": key, "analysis_type": "want_cutback", "recipe": recipe}
                )
                db.add(insight)
                created += 1

        db.commit()
        return {"created": created, "analyzed_days": days}
    finally:
        db.close()

@app.get("/advice/latest", response_model=List[AdviceOut])
def get_latest_advice(limit: int = 20):
    """
    Get the latest financial advice insights.
    """
    db = SessionLocal()
    try:
        insights = (
            db.query(AdviceInsight)
            .order_by(AdviceInsight.created_at.desc())
            .limit(limit)
            .all()
        )

        return [
            AdviceOut(
                id=insight.id,
                created_at=insight.created_at.isoformat(),
                kind=insight.kind,
                title=insight.title,
                body=insight.body,
                monthly_saving=insight.monthly_saving,
                annual_saving=insight.annual_saving,
                projection_10y=insight.projection_10y,
                confidence=insight.confidence,
                tx_ids=insight.tx_ids or [],
                meta=insight.meta or {},
            )
            for insight in insights
        ]
    finally:
        db.close()

@app.delete("/advice/{advice_id}")
def delete_advice(advice_id: int):
    """Delete a specific advice insight."""
    db = SessionLocal()
    try:
        insight = db.query(AdviceInsight).filter(AdviceInsight.id == advice_id).first()
        if not insight:
            raise HTTPException(status_code=404, detail="Advice not found")
        
        db.delete(insight)
        db.commit()
        return {"message": "Advice deleted successfully"}
    finally:
        db.close()

# ---------- SEED DATA ROUTES ----------
@app.post("/seed/benchmarks")
def seed_benchmark_data():
    """Seed some sample provider benchmark data for testing."""
    db = SessionLocal()
    try:
        db.query(ProviderBenchmark).delete()
        
        sample_benchmarks = [
            {"provider": "Vodafone", "plan": "SIM-only 20GB", "monthly_price": 20.0, "category": "telecom"},
            {"provider": "Three IE", "plan": "SIM-only 20GB", "monthly_price": 15.0, "category": "telecom"},
            {"provider": "Eir", "plan": "SIM-only 20GB", "monthly_price": 18.0, "category": "telecom"},
            {"provider": "Netflix", "plan": "Standard", "monthly_price": 12.99, "category": "streaming"},
            {"provider": "Amazon Prime", "plan": "Monthly", "monthly_price": 8.99, "category": "streaming"},
            {"provider": "Disney+", "plan": "Monthly", "monthly_price": 8.99, "category": "streaming"},
            {"provider": "Spotify", "plan": "Premium", "monthly_price": 9.99, "category": "streaming"},
            {"provider": "Apple Music", "plan": "Individual", "monthly_price": 9.99, "category": "streaming"},
        ]
        
        for benchmark in sample_benchmarks:
            db.add(ProviderBenchmark(**benchmark))
        
        db.commit()
        return {"message": f"Seeded {len(sample_benchmarks)} benchmark records"}
    finally:
        db.close()

@app.post("/seed/homebrew")
def seed_homebrew_data():
    """Seed some sample homebrew cost data for testing."""
    db = SessionLocal()
    try:
        db.query(HomebrewCost).delete()
        
        sample_costs = [
            {"item": "coffee", "estimated_unit_cost": 0.50},
            {"item": "burger", "estimated_unit_cost": 2.00},
            {"item": "sandwich", "estimated_unit_cost": 1.50},
            {"item": "pizza", "estimated_unit_cost": 3.00},
            {"item": "smoothie", "estimated_unit_cost": 1.00},
        ]
        
        for cost in sample_costs:
            db.add(HomebrewCost(**cost))
        
        db.commit()
        return {"message": f"Seeded {len(sample_costs)} homebrew cost records"}
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)