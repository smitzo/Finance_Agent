"""tenant workflow columns

Revision ID: 0001_tenant_workflow_columns
Revises:
Create Date: 2026-06-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_tenant_workflow_columns"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table_name in (
        "carriers",
        "carrier_contracts",
        "shipments",
        "bills_of_lading",
        "freight_bills",
        "audit_logs",
    ):
        op.add_column(
            table_name,
            sa.Column("tenant_id", sa.String(length=64), nullable=False, server_default="default"),
        )
        op.create_index(f"ix_{table_name}_tenant_id", table_name, ["tenant_id"])

    op.add_column(
        "freight_bills",
        sa.Column("workflow_type", sa.String(length=50), nullable=False, server_default="freight_audit"),
    )

    op.drop_constraint("uq_freight_bills_carrier_bill_number", "freight_bills", type_="unique")
    op.create_unique_constraint(
        "uq_freight_bills_tenant_carrier_bill_number",
        "freight_bills",
        ["tenant_id", "carrier_id", "bill_number"],
    )
    op.create_unique_constraint("uq_carriers_tenant_code", "carriers", ["tenant_id", "carrier_code"])

    op.create_index("ix_carriers_tenant_status", "carriers", ["tenant_id", "status"])
    op.create_index("ix_contracts_tenant_carrier_status", "carrier_contracts", ["tenant_id", "carrier_id", "status"])
    op.create_index("ix_shipments_tenant_carrier_lane", "shipments", ["tenant_id", "carrier_id", "lane"])
    op.create_index("ix_bols_tenant_shipment", "bills_of_lading", ["tenant_id", "shipment_id"])
    op.create_index("ix_freight_bills_tenant_status_created", "freight_bills", ["tenant_id", "status", "created_at"])
    op.create_index("ix_freight_bills_tenant_workflow_status", "freight_bills", ["tenant_id", "workflow_type", "status"])
    op.create_index("ix_freight_bills_tenant_shipment", "freight_bills", ["tenant_id", "shipment_reference"])
    op.create_index("ix_audit_logs_tenant_bill_created", "audit_logs", ["tenant_id", "freight_bill_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_tenant_bill_created", table_name="audit_logs")
    op.drop_index("ix_freight_bills_tenant_shipment", table_name="freight_bills")
    op.drop_index("ix_freight_bills_tenant_workflow_status", table_name="freight_bills")
    op.drop_index("ix_freight_bills_tenant_status_created", table_name="freight_bills")
    op.drop_index("ix_bols_tenant_shipment", table_name="bills_of_lading")
    op.drop_index("ix_shipments_tenant_carrier_lane", table_name="shipments")
    op.drop_index("ix_contracts_tenant_carrier_status", table_name="carrier_contracts")
    op.drop_index("ix_carriers_tenant_status", table_name="carriers")

    op.drop_constraint("uq_carriers_tenant_code", "carriers", type_="unique")
    op.drop_constraint("uq_freight_bills_tenant_carrier_bill_number", "freight_bills", type_="unique")
    op.create_unique_constraint(
        "uq_freight_bills_carrier_bill_number",
        "freight_bills",
        ["carrier_id", "bill_number"],
    )
    op.drop_column("freight_bills", "workflow_type")

    for table_name in (
        "audit_logs",
        "freight_bills",
        "bills_of_lading",
        "shipments",
        "carrier_contracts",
        "carriers",
    ):
        op.drop_index(f"ix_{table_name}_tenant_id", table_name=table_name)
        op.drop_column(table_name, "tenant_id")
