"""Optimize position storage and enable TimescaleDB when available."""
from alembic import op
import sqlalchemy as sa

revision = "0002_telemetry_timeseries"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        # TimescaleDB is optional; managed PostgreSQL without the extension
        # still receives the ordinary indexes below.
        try:
            bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
            bind.execute(sa.text("SELECT create_hypertable('positions', 'recorded_at', if_not_exists => TRUE)"))
        except Exception:
            # TimescaleDB is optional. Roll back the failed extension statement
            # before continuing with ordinary PostgreSQL indexes.
            bind.rollback()
    existing = {item["name"] for item in sa.inspect(bind).get_indexes("positions")}
    if "ix_positions_vehicle_recorded" not in existing:
        op.create_index("ix_positions_vehicle_recorded", "positions", ["organization_id", "vehicle_id", "recorded_at"], unique=False)
    if "ix_positions_device_recorded" not in existing:
        op.create_index("ix_positions_device_recorded", "positions", ["device_imei", "recorded_at"], unique=False)

def downgrade():
    op.drop_index("ix_positions_device_recorded", table_name="positions")
    op.drop_index("ix_positions_vehicle_recorded", table_name="positions")
