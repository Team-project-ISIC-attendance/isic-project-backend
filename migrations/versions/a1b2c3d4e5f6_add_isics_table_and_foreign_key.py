import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision = 'a1b2c3d4e5f6'
down_revision = 'f2e7dd1f048d'
branch_labels = None
depends_on = None

DEFAULT_FIRST_NAME = 'Unknown'
DEFAULT_LAST_NAME = 'Unknown'
FOREIGN_KEY_NAME = 'fk_isic_scans_isic_id_isics'


def get_unique_identifiers_from_scans(connection: Connection) -> list[str]:
    result = connection.execute(sa.text("SELECT DISTINCT isic_identifier FROM isic_scans"))
    return [row[0] for row in result]


def create_isic_records_for_identifiers(connection: Connection, identifiers: list[str]) -> None:
    for identifier in identifiers:
        connection.execute(sa.text(
            "INSERT INTO isics (isic_identifier, first_name, last_name, created_at) "
            "VALUES (:identifier, :first_name, :last_name, datetime('now'))"
        ), {
            'identifier': identifier,
            'first_name': DEFAULT_FIRST_NAME,
            'last_name': DEFAULT_LAST_NAME,
        })


def populate_isic_id_in_scans(connection: Connection) -> None:
    connection.execute(sa.text(
        "UPDATE isic_scans "
        "SET isic_id = (SELECT id FROM isics WHERE isics.isic_identifier = isic_scans.isic_identifier)"
    ))


def populate_isic_identifier_in_scans(connection: Connection) -> None:
    connection.execute(sa.text(
        "UPDATE isic_scans "
        "SET isic_identifier = (SELECT isic_identifier FROM isics WHERE isics.id = isic_scans.isic_id)"
    ))


def upgrade() -> None:
    op.create_table('isics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('isic_identifier', sa.String(), nullable=False),
        sa.Column('first_name', sa.String(), nullable=False),
        sa.Column('last_name', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_isics_id'), 'isics', ['id'], unique=False)
    op.create_index(op.f('ix_isics_isic_identifier'), 'isics', ['isic_identifier'], unique=True)
    
    connection = op.get_bind()
    unique_identifiers = get_unique_identifiers_from_scans(connection)
    create_isic_records_for_identifiers(connection, unique_identifiers)
    
    op.add_column('isic_scans', sa.Column('isic_id', sa.Integer(), nullable=True))
    populate_isic_id_in_scans(connection)
    
    with op.batch_alter_table('isic_scans', schema=None) as batch_op:
        batch_op.alter_column('isic_id', nullable=False)
        batch_op.create_foreign_key(
            FOREIGN_KEY_NAME,
            'isics',
            ['isic_id'], ['id']
        )
        batch_op.create_index(op.f('ix_isic_scans_isic_id'), ['isic_id'], unique=False)
    
    op.drop_index(op.f('ix_isic_scans_isic_identifier'), table_name='isic_scans')
    op.drop_column('isic_scans', 'isic_identifier')


def downgrade() -> None:
    op.add_column('isic_scans', sa.Column('isic_identifier', sa.String(), nullable=True))
    
    connection = op.get_bind()
    populate_isic_identifier_in_scans(connection)
    
    with op.batch_alter_table('isic_scans', schema=None) as batch_op:
        batch_op.alter_column('isic_identifier', nullable=False)
    
    op.create_index(op.f('ix_isic_scans_isic_identifier'), 'isic_scans', ['isic_identifier'], unique=False)
    
    op.drop_index(op.f('ix_isic_scans_isic_id'), table_name='isic_scans')
    op.drop_constraint(FOREIGN_KEY_NAME, 'isic_scans', type_='foreignkey')
    op.drop_column('isic_scans', 'isic_id')
    
    op.drop_index(op.f('ix_isics_isic_identifier'), table_name='isics')
    op.drop_index(op.f('ix_isics_id'), table_name='isics')
    op.drop_table('isics')

