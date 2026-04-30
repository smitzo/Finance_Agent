"""freight bill idempotency

Revision ID: 0002_freight_bill_idempotency
Revises: 0001_tenant_workflow_columns
Create Date: 2026-06-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_freight_bill_idempotency"
down_revision = "0001_tenant_workflow_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("freight_bills", sa.Column("idempotency_key", sa.String(length=100), nullable=True))
    op.create_unique_constraint(
        "uq_freight_bills_tenant_workflow_idempotency",
        "freight_bills",
        ["tenant_id", "workflow_type", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_freight_bills_tenant_workflow_idempotency", "freight_bills", type_="unique")
    op.drop_column("freight_bills", "idempotency_key")
