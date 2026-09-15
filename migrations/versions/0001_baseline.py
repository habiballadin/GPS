"""Baseline schema for the GPS fleet platform."""
from alembic import op
from app.db import Base
from app import models  # noqa: F401

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    Base.metadata.create_all(bind=op.get_bind())

def downgrade():
    # Baseline is non-destructive; use explicit follow-up revisions for drops.
    pass
