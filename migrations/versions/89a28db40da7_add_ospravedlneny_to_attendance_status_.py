"""add ospravedlneny to attendance status enum

Revision ID: 89a28db40da7
Revises: ac528ce30b21
Create Date: 2026-04-28 21:53:02.268351

"""

# revision identifiers, used by Alembic.
revision = '89a28db40da7'
down_revision = 'ac528ce30b21'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite stores enums as TEXT — no schema change needed.
    # The new "ospravedlneny" value is enforced at the Python/SQLAlchemy level.
    pass


def downgrade() -> None:
    # No schema change to revert.
    pass
