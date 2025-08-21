from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, Numeric, Boolean, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, default="Main")
    currency = Column(String(10), nullable=False, default="EUR")
    transactions = relationship("Transaction", back_populates="account")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    date = Column(Date, nullable=False)
    description = Column(String(255), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)  # positive income / negative spend
    merchant_raw = Column(String(255))
    metadata_json = Column(Text) 

    account = relationship("Account", back_populates="transactions")
    enriched = relationship("EnrichedTransaction", uselist=False, back_populates="transaction")

class EnrichedTransaction(Base):
    __tablename__ = "enriched_transactions"
    transaction_id = Column(Integer, ForeignKey("transactions.id"), primary_key=True)
    merchant = Column(String(255))
    category = Column(String(64))
    subcategory = Column(String(64))
    is_subscription = Column(Boolean, default=False)
    confidence = Column(Numeric(3, 2))  
    notes = Column(Text)

    transaction = relationship("Transaction", back_populates="enriched")
