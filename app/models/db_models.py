"""
SQLAlchemy ORM models.

Relational layer stores freight bills, decisions, and audit trail.
Graph relationships are maintained in-memory via NetworkX (built at startup from
the same Postgres tables — no separate graph DB needed for this scale).
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, JSON,
    ForeignKey, Enum as SAEnum, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


# Reference data (loaded from seed) 

class Carrier(Base):
    __tablename__ = "carriers"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    carrier_code = Column(String(10), nullable=False)
    gstin = Column(String(20))
    bank_account = Column(String(50))
    status = Column(String(20), default="active")
    onboarded_on = Column(String(20))

    contracts = relationship("CarrierContract", back_populates="carrier")
    shipments = relationship("Shipment", back_populates="carrier")


class CarrierContract(Base):
    __tablename__ = "carrier_contracts"

    id = Column(String, primary_key=True)
    carrier_id = Column(String, ForeignKey("carriers.id"), nullable=False)
    effective_date = Column(String(20), nullable=False)
    expiry_date = Column(String(20), nullable=False)
    status = Column(String(20), default="active")
    notes = Column(Text)
    rate_card = Column(JSON, nullable=False)

    carrier = relationship("Carrier", back_populates="contracts")
    shipments = relationship("Shipment", back_populates="contract")


class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(String, primary_key=True)
    carrier_id = Column(String, ForeignKey("carriers.id"), nullable=False)
    contract_id = Column(String, ForeignKey("carrier_contracts.id"), nullable=True)
    lane = Column(String(30), nullable=False)
    shipment_date = Column(String(20))
    status = Column(String(30))
    total_weight_kg = Column(Float)
    notes = Column(Text)

    carrier = relationship("Carrier", back_populates="shipments")
    contract = relationship("CarrierContract", back_populates="shipments")
    bols = relationship("BillOfLading", back_populates="shipment")


class BillOfLading(Base):
    __tablename__ = "bills_of_lading"

    id = Column(String, primary_key=True)
    shipment_id = Column(String, ForeignKey("shipments.id"), nullable=False)
    delivery_date = Column(String(20))
    actual_weight_kg = Column(Float)
    notes = Column(Text)

    shipment = relationship("Shipment", back_populates="bols")


# ── Transactional data ────────────────────────────────────────────────────────

class FreightBillStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    awaiting_review = "awaiting_review"
    approved = "approved"
    disputed = "disputed"
    rejected = "rejected"


class FreightBill(Base):
    __tablename__ = "freight_bills"
    __table_args__ = (
        UniqueConstraint("carrier_id", "bill_number", name="uq_freight_bills_carrier_bill_number"),
    )

    id = Column(String, primary_key=True)
    carrier_id = Column(String, nullable=True)
    carrier_name = Column(String, nullable=False)
    bill_number = Column(String, nullable=False)
    bill_date = Column(String(20))
    shipment_reference = Column(String, nullable=True)
    lane = Column(String(30))
    billed_weight_kg = Column(Float)
    rate_per_kg = Column(Float)
    billing_unit = Column(String(20), default="kg")
    base_charge = Column(Float)
    fuel_surcharge = Column(Float)
    gst_amount = Column(Float)
    total_amount = Column(Float)

    # Processing state
    status = Column(SAEnum(FreightBillStatus), default=FreightBillStatus.pending)
    confidence_score = Column(Float, nullable=True)
    decision = Column(String(30), nullable=True)
    decision_reason = Column(Text, nullable=True)
    evidence = Column(JSON, nullable=True)

    # Human review
    reviewer_decision = Column(String(30), nullable=True)
    reviewer_notes = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    # LangGraph thread id for resuming
    thread_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    audit_entries = relationship(
        "AuditLog", back_populates="freight_bill", order_by="AuditLog.created_at"
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    freight_bill_id = Column(String, ForeignKey("freight_bills.id"), nullable=False)
    event = Column(String(80), nullable=False)
    detail = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    freight_bill = relationship("FreightBill", back_populates="audit_entries")
