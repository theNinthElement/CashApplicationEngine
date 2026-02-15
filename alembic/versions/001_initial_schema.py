"""Initial schema with all tables

Revision ID: 001_initial
Revises:
Create Date: 2026-02-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create match_status enum
    match_status_enum = postgresql.ENUM(
        'unmatched', 'matched', 'manual_review',
        name='matchstatus',
        create_type=True
    )
    match_status_enum.create(op.get_bind(), checkfirst=True)

    # Create remittance_status enum
    remittance_status_enum = postgresql.ENUM(
        'unmatched', 'matched', 'partial',
        name='remittancestatus',
        create_type=True
    )
    remittance_status_enum.create(op.get_bind(), checkfirst=True)

    # Create match_type enum
    match_type_enum = postgresql.ENUM(
        'auto_exact', 'auto_fuzzy', 'manual',
        name='matchtype',
        create_type=True
    )
    match_type_enum.create(op.get_bind(), checkfirst=True)

    # Create bank_transactions table
    op.create_table(
        'bank_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('buchungsdatum', sa.Date(), nullable=False),
        sa.Column('betrag', sa.Numeric(15, 2), nullable=False),
        sa.Column('auftraggeber_empfaenger', sa.String(255), nullable=True),
        sa.Column('kundenreferenz', sa.String(255), nullable=True, index=True),
        sa.Column('verwendungszweck', sa.Text(), nullable=True),
        sa.Column('currency', sa.String(3), default='EUR'),
        sa.Column('match_status', match_status_enum, default='unmatched'),
        sa.Column('valutadatum', sa.Date(), nullable=True),
        sa.Column('buchungstext', sa.String(255), nullable=True),
        sa.Column('bic', sa.String(11), nullable=True),
        sa.Column('iban', sa.String(34), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create remittance_advices table
    op.create_table(
        'remittance_advices',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_number', sa.String(50), nullable=False, index=True),
        sa.Column('sender_name', sa.String(255), nullable=True),
        sa.Column('sender_address', sa.Text(), nullable=True),
        sa.Column('document_date', sa.Date(), nullable=True),
        sa.Column('total_gross_amount', sa.Numeric(15, 2), nullable=True),
        sa.Column('total_discount', sa.Numeric(15, 2), nullable=True),
        sa.Column('total_net_amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('currency', sa.String(3), default='EUR'),
        sa.Column('match_status', remittance_status_enum, default='unmatched'),
        sa.Column('source_file', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create remittance_line_items table
    op.create_table(
        'remittance_line_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('remittance_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('remittance_advices.id'), nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=False),
        sa.Column('ihre_belegnr', sa.String(50), nullable=True),
        sa.Column('referenz', sa.String(50), nullable=True),
        sa.Column('skonto', sa.Numeric(15, 2), nullable=True, default=0),
        sa.Column('bruttobetrag', sa.Numeric(15, 2), nullable=True),
        sa.Column('zahlbetrag', sa.Numeric(15, 2), nullable=False),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
    )

    # Create matches table
    op.create_table(
        'matches',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('transaction_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('bank_transactions.id'), nullable=False),
        sa.Column('remittance_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('remittance_advices.id'), nullable=False),
        sa.Column('confidence_score', sa.Numeric(5, 2), nullable=False),
        sa.Column('match_type', match_type_enum, nullable=False),
        sa.Column('match_details', postgresql.JSONB(), nullable=True),
        sa.Column('approved', sa.Boolean(), default=False),
        sa.Column('approved_by', sa.String(100), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create journal_entries table
    op.create_table(
        'journal_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('match_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('matches.id'), nullable=True),
        sa.Column('remittance_line_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('remittance_line_items.id'), nullable=True),
        sa.Column('company_code', sa.String(10), default='1000'),
        sa.Column('posting_date', sa.Date(), nullable=False),
        sa.Column('document_date', sa.Date(), nullable=False),
        sa.Column('document_type', sa.String(10), default='SA'),
        sa.Column('line_number', sa.Integer(), nullable=False),
        sa.Column('gl_account', sa.String(20), default='100000'),
        sa.Column('debit', sa.Numeric(15, 2), nullable=True),
        sa.Column('credit', sa.Numeric(15, 2), nullable=True),
        sa.Column('currency', sa.String(3), default='EUR'),
        sa.Column('item_text', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('journal_entries')
    op.drop_table('matches')
    op.drop_table('remittance_line_items')
    op.drop_table('remittance_advices')
    op.drop_table('bank_transactions')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS matchtype')
    op.execute('DROP TYPE IF EXISTS remittancestatus')
    op.execute('DROP TYPE IF EXISTS matchstatus')
