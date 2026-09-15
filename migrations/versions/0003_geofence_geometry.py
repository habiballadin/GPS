"""Add polygon and corridor geofence geometry."""
from alembic import op
import sqlalchemy as sa

revision = "0003_geofence_geometry"
down_revision = "0002_telemetry_timeseries"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("geofences", sa.Column("geofence_type", sa.String(length=20), nullable=False, server_default="circle"))
    op.add_column("geofences", sa.Column("geometry", sa.JSON(), nullable=True))
    op.add_column("geofences", sa.Column("corridor_width_m", sa.Float(), nullable=True))

def downgrade():
    op.drop_column("geofences", "corridor_width_m")
    op.drop_column("geofences", "geometry")
    op.drop_column("geofences", "geofence_type")
