"""add student metadata to isics

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-05-05 23:25:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("isics", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("student_identifier", sa.String(), nullable=True)
        )
        batch_op.add_column(sa.Column("full_name", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("study_identification", sa.String(), nullable=True)
        )
        batch_op.add_column(sa.Column("email_is", sa.String(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_isics_student_identifier"),
            ["student_identifier"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("isics", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_isics_student_identifier"))
        batch_op.drop_column("email_is")
        batch_op.drop_column("study_identification")
        batch_op.drop_column("full_name")
        batch_op.drop_column("student_identifier")
