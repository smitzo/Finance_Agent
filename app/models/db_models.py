"""
SQLAlchemy ORM models.

Relational layer stores tenant-scoped freight data, decisions, and audit trail.
Neo4j is the production graph traversal store; the relational tables remain the
source of truth for billing workflow state.
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, JSON,
    ForeignKey, Enum as SAEnum, UniqueConstraint, Index,
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum

from app.workflows import FREIGHT_AUDIT


class Base(DeclarativeBase):
    pass


class PartnerFirm(Base):
    __tablename__ = "partner_firms"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_partner_firms_tenant_name"),
        Index("ix_partner_firms_tenant_type", "tenant_id", "firm_type"),
    )

    id = Column(String, primary_key=True)
    tenant_id = Column(String(64), nullable=False, default="default", server_default="default", index=True)
    name = Column(String(200), nullable=False)
    firm_type = Column(String(50), nullable=False, default="ca_firm", server_default="ca_firm")
    registration_number = Column(String(80), nullable=True)
    gstin = Column(String(20), nullable=True)
    contact_name = Column(String(120), nullable=False)
    contact_email = Column(String(200), nullable=False)
    contact_phone = Column(String(40), nullable=True)
    status = Column(String(20), nullable=False, default="active", server_default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    companies = relationship("Company", back_populates="ca_partner_firm")


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "legal_name", name="uq_companies_tenant_legal_name"),
        Index("ix_companies_tenant_status", "tenant_id", "status"),
    )

    id = Column(String, primary_key=True)
    tenant_id = Column(String(64), nullable=False, default="default", server_default="default", index=True)
    legal_name = Column(String(200), nullable=False)
    display_name = Column(String(160), nullable=False)
    gstin = Column(String(20), nullable=True)
    country = Column(String(2), nullable=False, default="IN", server_default="IN")
    timezone = Column(String(60), nullable=False, default="Asia/Kolkata", server_default="Asia/Kolkata")
    billing_email = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default="active", server_default="active")
    ca_partner_firm_id = Column(String, ForeignKey("partner_firms.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    ca_partner_firm = relationship("PartnerFirm", back_populates="companies")
    users = relationship("AppUser", back_populates="company")


class AppUser(Base):
    __tablename__ = "app_users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="uq_app_users_tenant_username"),
        Index("ix_app_users_tenant_role", "tenant_id", "role"),
    )

    id = Column(String, primary_key=True)
    tenant_id = Column(String(64), nullable=False, default="default", server_default="default", index=True)
    company_id = Column(String, ForeignKey("companies.id"), nullable=True)
    username = Column(String(80), nullable=False)
    display_name = Column(String(120), nullable=False)
    email = Column(String(200), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False, default="operator", server_default="operator")
    status = Column(String(20), nullable=False, default="active", server_default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="users")


# Reference data (loaded from seed)

class Carrier(Base):
    __tablename__ = "carriers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "carrier_code", name="uq_carriers_tenant_code"),
        Index("ix_carriers_tenant_status", "tenant_id", "status"),
    )

    id = Column(String, primary_key=True)
    tenant_id = Column(String(64), nullable=False, default="default", server_default="default", index=True)
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
    __table_args__ = (
        Index("ix_contracts_tenant_carrier_status", "tenant_id", "carrier_id", "status"),
    )

    id = Column(String, primary_key=True)
    tenant_id = Column(String(64), nullable=False, default="default", server_default="default", index=True)
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
    __table_args__ = (
        Index("ix_shipments_tenant_carrier_lane", "tenant_id", "carrier_id", "lane"),
    )

    id = Column(String, primary_key=True)
    tenant_id = Column(String(64), nullable=False, default="default", server_default="default", index=True)
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
    __table_args__ = (
        Index("ix_bols_tenant_shipment", "tenant_id", "shipment_id"),
    )

    id = Column(String, primary_key=True)
    tenant_id = Column(String(64), nullable=False, default="default", server_default="default", index=True)
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
        UniqueConstraint("tenant_id", "carrier_id", "bill_number", name="uq_freight_bills_tenant_carrier_bill_number"),
        UniqueConstraint("tenant_id", "workflow_type", "idempotency_key", name="uq_freight_bills_tenant_workflow_idempotency"),
        Index("ix_freight_bills_tenant_status_created", "tenant_id", "status", "created_at"),
        Index("ix_freight_bills_tenant_workflow_status", "tenant_id", "workflow_type", "status"),
        Index("ix_freight_bills_tenant_shipment", "tenant_id", "shipment_reference"),
    )

    id = Column(String, primary_key=True)
    tenant_id = Column(String(64), nullable=False, default="default", server_default="default", index=True)
    workflow_type = Column(String(50), nullable=False, default=FREIGHT_AUDIT, server_default=FREIGHT_AUDIT)
    idempotency_key = Column(String(100), nullable=True)
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
    __table_args__ = (
        Index("ix_audit_logs_tenant_bill_created", "tenant_id", "freight_bill_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), nullable=False, default="default", server_default="default", index=True)
    freight_bill_id = Column(String, ForeignKey("freight_bills.id"), nullable=False)
    event = Column(String(80), nullable=False)
    detail = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    freight_bill = relationship("FreightBill", back_populates="audit_entries")
