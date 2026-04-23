"""Initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-23 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums (use DO blocks for IF NOT EXISTS support) ─────────────────────
    enums = {
        "kyc_status_enum": ("PENDING", "APPROVED", "REJECTED"),
        "account_type_enum": ("FIAT", "CRYPTO", "RESERVE"),
        "bank_account_status_enum": ("PENDING", "ACTIVE", "INACTIVE", "REJECTED"),
        "asset_type_enum": ("CRYPTO", "FIAT", "STOCK", "COMMODITY"),
        "order_side_enum": ("BUY", "SELL"),
        "order_type_enum": ("MARKET", "LIMIT"),
        "order_status_enum": ("PENDING", "PARTIALLY_FILLED", "FILLED", "FAILED", "CANCELLED"),
        "transaction_type_enum": ("DEPOSIT", "WITHDRAW", "TRADE", "FEE"),
        "transaction_status_enum": ("PENDING", "PROCESSING", "COMPLETED", "FAILED", "REVERSED"),
    }
    for name, values in enums.items():
        values_str = ", ".join(f"'{v}'" for v in values)
        op.execute(sa.text(
            f"DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{name}') THEN "
            f"CREATE TYPE {name} AS ENUM ({values_str}); "
            f"END IF; END $$;"
        ))

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("hashed_password", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── user_profiles ─────────────────────────────────────────────────────────
    op.create_table(
        "user_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("tax_id", sa.String(64), nullable=True),
        sa.Column("kyc_status", postgresql.ENUM("PENDING", "APPROVED", "REJECTED", name="kyc_status_enum", create_type=False), nullable=False, server_default="PENDING"),
        sa.Column("country", sa.String(2), nullable=False, server_default="BR"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_user_profiles_user_id"),
    )
    op.create_index("ix_user_profiles_user_id", "user_profiles", ["user_id"])

    # ── accounts ──────────────────────────────────────────────────────────────
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("account_type", postgresql.ENUM("FIAT", "CRYPTO", "RESERVE", name="account_type_enum", create_type=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "currency", name="uq_accounts_user_currency"),
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])

    # ── bank_accounts ─────────────────────────────────────────────────────────
    op.create_table(
        "bank_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_reference", sa.String(255), nullable=False),
        sa.Column("bank_name", sa.String(100), nullable=False),
        sa.Column("status", postgresql.ENUM("PENDING", "ACTIVE", "INACTIVE", "REJECTED", name="bank_account_status_enum", create_type=False), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_bank_accounts_user_id", "bank_accounts", ["user_id"])

    # ── assets ────────────────────────────────────────────────────────────────
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("asset_type", postgresql.ENUM("CRYPTO", "FIAT", "STOCK", "COMMODITY", name="asset_type_enum", create_type=False), nullable=False),
        sa.Column("network", sa.String(50), nullable=True),
        sa.Column("precision", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_assets_symbol", "assets", ["symbol"], unique=True)

    # ── orders ────────────────────────────────────────────────────────────────
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("side", postgresql.ENUM("BUY", "SELL", name="order_side_enum", create_type=False), nullable=False),
        sa.Column("order_type", postgresql.ENUM("MARKET", "LIMIT", name="order_type_enum", create_type=False), nullable=False),
        sa.Column("amount", sa.Numeric(36, 18), nullable=False),
        sa.Column("filled_amount", sa.Numeric(36, 18), nullable=False, server_default="0"),
        sa.Column("price", sa.Numeric(36, 18), nullable=True),
        sa.Column("status", postgresql.ENUM("PENDING", "PARTIALLY_FILLED", "FILLED", "FAILED", "CANCELLED", name="order_status_enum", create_type=False), nullable=False, server_default="PENDING"),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("idempotency_key", name="uq_orders_idempotency_key"),
    )
    op.create_index("ix_orders_user_id_status", "orders", ["user_id", "status"])
    op.create_index("ix_orders_asset_id", "orders", ["asset_id"])
    op.create_index("ix_orders_status", "orders", ["status"])

    # ── trade_executions ──────────────────────────────────────────────────────
    op.create_table(
        "trade_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("executed_price", sa.Numeric(36, 18), nullable=False),
        sa.Column("executed_amount", sa.Numeric(36, 18), nullable=False),
        sa.Column("fee", sa.Numeric(36, 18), nullable=False, server_default="0"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_fill_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_trade_executions_order_id", "trade_executions", ["order_id"])

    # ── positions ─────────────────────────────────────────────────────────────
    op.create_table(
        "positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(36, 18), nullable=False, server_default="0"),
        sa.Column("average_price", sa.Numeric(36, 18), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "asset_id", name="uq_positions_user_asset"),
    )
    op.create_index("ix_positions_user_id", "positions", ["user_id"])

    # ── transactions ──────────────────────────────────────────────────────────
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_type", postgresql.ENUM("DEPOSIT", "WITHDRAW", "TRADE", "FEE", name="transaction_type_enum", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM("PENDING", "PROCESSING", "COMPLETED", "FAILED", "REVERSED", name="transaction_status_enum", create_type=False), nullable=False, server_default="PENDING"),
        sa.Column("reference_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_transactions_user_id_status", "transactions", ["user_id", "status"])
    op.create_index("ix_transactions_reference_id", "transactions", ["reference_id"])
    op.create_index("ix_transactions_status", "transactions", ["status"])

    # ── ledger_entries ────────────────────────────────────────────────────────
    # CRITICAL: append-only, never updated or deleted.
    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("debit_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credit_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(36, 18), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("reference_type", sa.String(50), nullable=False),
        sa.Column("reference_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["debit_account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["credit_account_id"], ["accounts.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_ledger_debit_account_id", "ledger_entries", ["debit_account_id"])
    op.create_index("ix_ledger_credit_account_id", "ledger_entries", ["credit_account_id"])
    op.create_index("ix_ledger_reference", "ledger_entries", ["reference_type", "reference_id"])


def downgrade() -> None:
    op.drop_table("ledger_entries")
    op.drop_table("transactions")
    op.drop_table("positions")
    op.drop_table("trade_executions")
    op.drop_table("orders")
    op.drop_table("assets")
    op.drop_table("bank_accounts")
    op.drop_table("accounts")
    op.drop_table("user_profiles")
    op.drop_table("users")

    for enum_name in [
        "kyc_status_enum", "account_type_enum", "bank_account_status_enum",
        "asset_type_enum", "order_side_enum", "order_type_enum", "order_status_enum",
        "transaction_type_enum", "transaction_status_enum",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
