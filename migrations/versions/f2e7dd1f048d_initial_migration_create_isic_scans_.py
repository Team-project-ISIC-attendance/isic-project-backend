import sqlalchemy as sa
from alembic import op

revision = 'f2e7dd1f048d'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('isic_scans',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('isic_identifier', sa.String(), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_isic_scans_id'), 'isic_scans', ['id'], unique=False)
    op.create_index(op.f('ix_isic_scans_isic_identifier'), 'isic_scans', ['isic_identifier'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_isic_scans_isic_identifier'), table_name='isic_scans')
    op.drop_index(op.f('ix_isic_scans_id'), table_name='isic_scans')
    op.drop_table('isic_scans')

