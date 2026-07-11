"""Single import point for SQLAlchemy models, used by Alembic autogenerate.

Import every model module here so `Base.metadata` is fully populated when
Alembic compares it against the database. The app itself doesn't need this
module at runtime.
"""

from app.db.session import Base  # noqa: F401

# from app.models.something import Something  # noqa: F401
