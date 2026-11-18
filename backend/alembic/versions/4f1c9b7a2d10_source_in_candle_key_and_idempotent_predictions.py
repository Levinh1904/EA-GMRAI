"""data integrity: source in candle key + one prediction per bar

Revision ID: 4f1c9b7a2d10
Revises: 8ab6ee0542c9
Create Date: 2026-11-12 15:05:00.000000

Two fixes:
1. `market_candles` unique key gains `source`, so a demo feed and the real
   FTMO feed can coexist for the same bar without overwriting each other.
2. `model_predictions` becomes unique per (model_version, symbol, timeframe,
   ts): repeated polling can no longer append duplicate rows or advance the
   hysteresis engine twice on the same candle. Existing duplicates are
   collapsed to the earliest row per bar (the first, genuine single step).
"""
from alembic import op

revision = "4f1c9b7a2d10"
down_revision = "8ab6ee0542c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Collapse historical duplicate predictions (keep the first step per bar).
    op.execute(
        """
        DELETE FROM model_predictions
        WHERE id NOT IN (
            SELECT MIN(id) FROM model_predictions
            GROUP BY model_version_id, symbol, timeframe, ts
        )
        """
    )

    with op.batch_alter_table("model_predictions") as batch:
        batch.create_unique_constraint(
            "uq_pred_bar", ["model_version_id", "symbol", "timeframe", "ts"]
        )

    with op.batch_alter_table("market_candles") as batch:
        batch.drop_constraint("uq_candle_key", type_="unique")
        batch.create_unique_constraint(
            "uq_candle_key", ["symbol", "timeframe", "source", "ts"]
        )


def downgrade() -> None:
    with op.batch_alter_table("market_candles") as batch:
        batch.drop_constraint("uq_candle_key", type_="unique")
        batch.create_unique_constraint("uq_candle_key", ["symbol", "timeframe", "ts"])

    with op.batch_alter_table("model_predictions") as batch:
        batch.drop_constraint("uq_pred_bar", type_="unique")
