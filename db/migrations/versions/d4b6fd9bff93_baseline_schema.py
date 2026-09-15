"""baseline schema

Revision ID: d4b6fd9bff93
Revises:
Create Date: 2026-09-15 15:39:13.343691

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4b6fd9bff93'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_SQL_PATH = Path(__file__).resolve().parents[2] / "schema.sql"


def upgrade() -> None:
    """Create the telemetry schema (idempotent — matches db/schema.sql)."""
    sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    for statement in filter(None, (s.strip() for s in sql.split(";"))):
        op.execute(statement)


def downgrade() -> None:
    """No-op: this baseline predates migrations and may already hold data.

    There is no earlier revision to downgrade to, and dropping the
    telemetry tables here would destroy production data. If a clean
    teardown is ever needed, do it explicitly outside of Alembic.
    """
    pass
