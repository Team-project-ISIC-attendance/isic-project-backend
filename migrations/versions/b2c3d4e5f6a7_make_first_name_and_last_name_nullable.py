from alembic import op

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('isics', schema=None) as batch_op:
        batch_op.alter_column('first_name', nullable=True)
        batch_op.alter_column('last_name', nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('isics', schema=None) as batch_op:
        batch_op.alter_column('first_name', nullable=False)
        batch_op.alter_column('last_name', nullable=False)

