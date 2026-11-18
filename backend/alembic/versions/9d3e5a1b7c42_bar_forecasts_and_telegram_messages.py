"""bar_forecasts + telegram_messages

Revision ID: 9d3e5a1b7c42
Revises: 4f1c9b7a2d10
Create Date: 2026-11-13 08:00:00.000000

Two new tables:
  * `bar_forecasts` — one next-bar directional forecast per closed M15 bar.
    The outcome columns stay NULL until the following bar closes, so accuracy
    is scored honestly instead of being overwritten by the prediction itself.
  * `telegram_messages` — full notification log with a `dedupe_key` unique
    constraint, so the same signal for the same bar can never be sent twice.
"""
from alembic import op
import sqlalchemy as sa

revision = "9d3e5a1b7c42"
down_revision = "4f1c9b7a2d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bar_forecasts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("probability_up", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("regime", sa.String(length=24), nullable=True),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("features_json", sa.JSON(), nullable=True),
        sa.Column("note", sa.String(length=256), nullable=True),
        sa.Column("actual_direction", sa.String(length=8), nullable=True),
        sa.Column("actual_open", sa.Float(), nullable=True),
        sa.Column("actual_close", sa.Float(), nullable=True),
        sa.Column("correct", sa.Boolean(), nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "timeframe", "ts", name="uq_forecast_bar"),
    )
    op.create_index(op.f("ix_bar_forecasts_symbol"), "bar_forecasts", ["symbol"], unique=False)
    op.create_index("ix_forecast_sym_tf_ts", "bar_forecasts", ["symbol", "timeframe", "ts"], unique=False)

    op.create_table(
        "telegram_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("signal", sa.String(length=16), nullable=True),
        sa.Column("previous_signal", sa.String(length=16), nullable=True),
        sa.Column("bar_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("text", sa.String(length=4096), nullable=False),
        sa.Column("reason", sa.String(length=256), nullable=True),
        sa.Column("chat_id", sa.String(length=64), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_telegram_dedupe"),
    )
    op.create_index("ix_telegram_created", "telegram_messages", ["created_at"], unique=False)
    op.create_index("ix_telegram_status", "telegram_messages", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_telegram_status", table_name="telegram_messages")
    op.drop_index("ix_telegram_created", table_name="telegram_messages")
    op.drop_table("telegram_messages")
    op.drop_index("ix_forecast_sym_tf_ts", table_name="bar_forecasts")
    op.drop_index(op.f("ix_bar_forecasts_symbol"), table_name="bar_forecasts")
    op.drop_table("bar_forecasts")
