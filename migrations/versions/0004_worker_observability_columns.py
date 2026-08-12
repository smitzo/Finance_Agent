"""worker observability columns

Revision ID: 0004_worker_observability
Revises: 0003_company_partner_auth_models
Create Date: 2026-08-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_worker_observability"
down_revision = "0003_company_partner_auth_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("freight_bills", sa.Column("correlation_id", sa.String(length=64), nullable=True))
    op.add_column("freight_bills", sa.Column("celery_task_id", sa.String(length=64), nullable=True))
    op.add_column("freight_bills", sa.Column("processing_started_at", sa.DateTime(), nullable=True))
    op.add_column("freight_bills", sa.Column("processing_completed_at", sa.DateTime(), nullable=True))
    op.create_index("ix_freight_bills_correlation_id", "freight_bills", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_freight_bills_correlation_id", table_name="freight_bills")
    op.drop_column("freight_bills", "processing_completed_at")
    op.drop_column("freight_bills", "processing_started_at")
    op.drop_column("freight_bills", "celery_task_id")
    op.drop_column("freight_bills", "correlation_id")
