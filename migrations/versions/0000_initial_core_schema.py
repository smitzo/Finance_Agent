"""initial core freight schema

Revision ID: 0000_initial_core_schema
Revises:
Create Date: 2026-08-07

This captures the schema that predated Alembic ownership. Existing deployments
already stamped at a later revision are unaffected; fresh databases can now be
created entirely with ``alembic upgrade head``.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0000_initial_core_schema"
down_revision = None
branch_labels = None
depends_on = None


freight_bill_status = sa.Enum(
    "pending",
    "processing",
    "awaiting_review",
    "approved",
    "disputed",
    "rejected",
    name="freightbillstatus",
)


def upgrade() -> None:
    op.create_table(
        "carriers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("carrier_code", sa.String(length=10), nullable=False),
        sa.Column("gstin", sa.String(length=20), nullable=True),
        sa.Column("bank_account", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("onboarded_on", sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "carrier_contracts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("carrier_id", sa.String(), nullable=False),
        sa.Column("effective_date", sa.String(length=20), nullable=False),
        sa.Column("expiry_date", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("rate_card", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["carrier_id"], ["carriers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "shipments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("carrier_id", sa.String(), nullable=False),
        sa.Column("contract_id", sa.String(), nullable=True),
        sa.Column("lane", sa.String(length=30), nullable=False),
        sa.Column("shipment_date", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=True),
        sa.Column("total_weight_kg", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["carrier_id"], ["carriers.id"]),
        sa.ForeignKeyConstraint(["contract_id"], ["carrier_contracts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "bills_of_lading",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("shipment_id", sa.String(), nullable=False),
        sa.Column("delivery_date", sa.String(length=20), nullable=True),
        sa.Column("actual_weight_kg", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "freight_bills",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("carrier_id", sa.String(), nullable=True),
        sa.Column("carrier_name", sa.String(), nullable=False),
        sa.Column("bill_number", sa.String(), nullable=False),
        sa.Column("bill_date", sa.String(length=20), nullable=True),
        sa.Column("shipment_reference", sa.String(), nullable=True),
        sa.Column("lane", sa.String(length=30), nullable=True),
        sa.Column("billed_weight_kg", sa.Float(), nullable=True),
        sa.Column("rate_per_kg", sa.Float(), nullable=True),
        sa.Column("billing_unit", sa.String(length=20), nullable=True),
        sa.Column("base_charge", sa.Float(), nullable=True),
        sa.Column("fuel_surcharge", sa.Float(), nullable=True),
        sa.Column("gst_amount", sa.Float(), nullable=True),
        sa.Column("total_amount", sa.Float(), nullable=True),
        sa.Column("status", freight_bill_status, nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("decision", sa.String(length=30), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("reviewer_decision", sa.String(length=30), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "carrier_id",
            "bill_number",
            name="uq_freight_bills_carrier_bill_number",
        ),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("freight_bill_id", sa.String(), nullable=False),
        sa.Column("event", sa.String(length=80), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["freight_bill_id"], ["freight_bills.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("freight_bills")
    op.drop_table("bills_of_lading")
    op.drop_table("shipments")
    op.drop_table("carrier_contracts")
    op.drop_table("carriers")
    freight_bill_status.drop(op.get_bind(), checkfirst=True)
