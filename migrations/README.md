# Database migrations

Set `AUTO_CREATE_SCHEMA=false` in production and run `alembic upgrade head`.
Create future revisions with `alembic revision --autogenerate -m "describe change"`, review the generated SQL, and deploy migrations before the application release.
