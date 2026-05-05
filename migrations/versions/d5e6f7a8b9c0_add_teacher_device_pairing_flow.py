"""add teacher device pairing flow

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-05-05 16:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("isic_identifier", sa.String(), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_users_isic_identifier"),
            ["isic_identifier"],
            unique=True,
        )

    with op.batch_alter_table("hardware_devices", schema=None) as batch_op:
        batch_op.add_column(sa.Column("teacher_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_hardware_devices_teacher_id"),
            ["teacher_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_hardware_devices_teacher_id",
            "users",
            ["teacher_id"],
            ["id"],
        )

    op.create_table(
        "device_pairing_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hardware_device_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "completed",
                "expired",
                "cancelled",
                name="devicepairingstatus",
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["hardware_device_id"], ["hardware_devices.id"]),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_device_pairing_sessions_id"),
        "device_pairing_sessions",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_device_pairing_sessions_hardware_device_id"),
        "device_pairing_sessions",
        ["hardware_device_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_device_pairing_sessions_teacher_id"),
        "device_pairing_sessions",
        ["teacher_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_device_pairing_sessions_teacher_id"),
        table_name="device_pairing_sessions",
    )
    op.drop_index(
        op.f("ix_device_pairing_sessions_hardware_device_id"),
        table_name="device_pairing_sessions",
    )
    op.drop_index(
        op.f("ix_device_pairing_sessions_id"),
        table_name="device_pairing_sessions",
    )
    op.drop_table("device_pairing_sessions")

    with op.batch_alter_table("hardware_devices", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_hardware_devices_teacher_id",
            type_="foreignkey",
        )
        batch_op.drop_index(batch_op.f("ix_hardware_devices_teacher_id"))
        batch_op.drop_column("claimed_at")
        batch_op.drop_column("teacher_id")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_isic_identifier"))
        batch_op.drop_column("isic_identifier")
