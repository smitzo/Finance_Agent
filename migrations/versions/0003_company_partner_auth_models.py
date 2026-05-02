"""company partner auth models

Revision ID: 0003_company_partner_auth_models
Revises: 0002_freight_bill_idempotency
Create Date: 2026-06-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_company_partner_auth_models"
down_revision = "0002_freight_bill_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partner_firms",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), server_default="default", nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("firm_type", sa.String(length=50), server_default="ca_firm", nullable=False),
        sa.Column("registration_number", sa.String(length=80), nullable=True),
        sa.Column("gstin", sa.String(length=20), nullable=True),
        sa.Column("contact_name", sa.String(length=120), nullable=False),
        sa.Column("contact_email", sa.String(length=200), nullable=False),
        sa.Column("contact_phone", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_partner_firms_tenant_name"),
    )
    op.create_index("ix_partner_firms_tenant_id", "partner_firms", ["tenant_id"])
    op.create_index("ix_partner_firms_tenant_type", "partner_firms", ["tenant_id", "firm_type"])

    op.create_table(
        "companies",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), server_default="default", nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("gstin", sa.String(length=20), nullable=True),
        sa.Column("country", sa.String(length=2), server_default="IN", nullable=False),
        sa.Column("timezone", sa.String(length=60), server_default="Asia/Kolkata", nullable=False),
        sa.Column("billing_email", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("ca_partner_firm_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["ca_partner_firm_id"], ["partner_firms.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "legal_name", name="uq_companies_tenant_legal_name"),
    )
    op.create_index("ix_companies_tenant_id", "companies", ["tenant_id"])
    op.create_index("ix_companies_tenant_status", "companies", ["tenant_id", "status"])

    op.create_table(
        "app_users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), server_default="default", nullable=False),
        sa.Column("company_id", sa.String(), nullable=True),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=30), server_default="operator", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "username", name="uq_app_users_tenant_username"),
    )
    op.create_index("ix_app_users_tenant_id", "app_users", ["tenant_id"])
    op.create_index("ix_app_users_tenant_role", "app_users", ["tenant_id", "role"])


def downgrade() -> None:
    op.drop_index("ix_app_users_tenant_role", table_name="app_users")
    op.drop_index("ix_app_users_tenant_id", table_name="app_users")
    op.drop_table("app_users")

    op.drop_index("ix_companies_tenant_status", table_name="companies")
    op.drop_index("ix_companies_tenant_id", table_name="companies")
    op.drop_table("companies")

    op.drop_index("ix_partner_firms_tenant_type", table_name="partner_firms")
    op.drop_index("ix_partner_firms_tenant_id", table_name="partner_firms")
    op.drop_table("partner_firms")
