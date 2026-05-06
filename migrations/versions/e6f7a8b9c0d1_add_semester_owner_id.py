"""add semester owner id

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-05-05 18:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("semesters", schema=None) as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_semesters_owner_id"),
            ["owner_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_semesters_owner_id",
            "users",
            ["owner_id"],
            ["id"],
        )

    conn = op.get_bind()

    semesters = sa.table(
        "semesters",
        sa.column("id", sa.Integer),
        sa.column("owner_id", sa.Integer),
    )
    schedule_entries = sa.table(
        "schedule_entries",
        sa.column("semester_id", sa.Integer),
        sa.column("subject_id", sa.Integer),
    )
    subjects = sa.table(
        "subjects",
        sa.column("id", sa.Integer),
        sa.column("teacher_id", sa.Integer),
    )
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("role", sa.String),
    )

    admin_id = conn.execute(
        sa.select(users.c.id)
        .where(users.c.role == "admin")
        .order_by(users.c.id)
        .limit(1)
    ).scalar_one_or_none()

    semester_ids = conn.execute(sa.select(semesters.c.id)).scalars().all()
    for semester_id in semester_ids:
        teacher_ids = conn.execute(
            sa.select(sa.distinct(subjects.c.teacher_id))
            .select_from(
                schedule_entries.join(
                    subjects,
                    schedule_entries.c.subject_id == subjects.c.id,
                )
            )
            .where(schedule_entries.c.semester_id == semester_id)
        ).scalars().all()

        owner_id = teacher_ids[0] if len(teacher_ids) == 1 else admin_id
        if owner_id is None:
            continue

        conn.execute(
            semesters.update()
            .where(semesters.c.id == semester_id)
            .values(owner_id=owner_id)
        )


def downgrade() -> None:
    with op.batch_alter_table("semesters", schema=None) as batch_op:
        batch_op.drop_constraint("fk_semesters_owner_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_semesters_owner_id"))
        batch_op.drop_column("owner_id")
