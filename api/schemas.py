from datetime import date
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class TransactionCreate(BaseModel):
    account_id: int = Field(1, description="Default to main account")
    date: date
    description: str
    amount: float
    merchant_raw: Optional[str] = None

class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    date: date
    description: str
    amount: float
    merchant_raw: Optional[str] = None

class EnrichedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    transaction_id: int
    merchant: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    is_subscription: Optional[bool] = None
    confidence: Optional[float] = None
    notes: Optional[str] = None
