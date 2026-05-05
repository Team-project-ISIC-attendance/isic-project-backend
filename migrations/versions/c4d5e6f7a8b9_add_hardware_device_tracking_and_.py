"""add hardware device tracking and snapshots

Revision ID: c4d5e6f7a8b9
Revises: 89a28db40da7
Create Date: 2026-05-05 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c4d5e6f7a8b9"
down_revision = "89a28db40da7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hardware_devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("base_topic", sa.String(), nullable=False),
        sa.Column("location_id", sa.String(), nullable=True),
        sa.Column("firmware", sa.String(), nullable=True),
        sa.Column("health_state", sa.String(), nullable=True),
        sa.Column("health_payload", sa.JSON(), nullable=True),
        sa.Column("metrics_payload", sa.JSON(), nullable=True),
        sa.Column("config_payload", sa.JSON(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attendance_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_metrics_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_config_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id"),
    )
    op.create_index(
        op.f("ix_hardware_devices_id"),
        "hardware_devices",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_hardware_devices_device_id"),
        "hardware_devices",
        ["device_id"],
        unique=False,
    )

    with op.batch_alter_table("isic_scans", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("hardware_device_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("mqtt_topic", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("mqtt_sequence", sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_isic_scans_hardware_device_id"),
            ["hardware_device_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_isic_scans_hardware_device_id",
            "hardware_devices",
            ["hardware_device_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("isic_scans", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_isic_scans_hardware_device_id",
            type_="foreignkey",
        )
        batch_op.drop_index(batch_op.f("ix_isic_scans_hardware_device_id"))
        batch_op.drop_column("mqtt_sequence")
        batch_op.drop_column("mqtt_topic")
        batch_op.drop_column("hardware_device_id")

    op.drop_index(op.f("ix_hardware_devices_device_id"), table_name="hardware_devices")
    op.drop_index(op.f("ix_hardware_devices_id"), table_name="hardware_devices")
    op.drop_table("hardware_devices")
