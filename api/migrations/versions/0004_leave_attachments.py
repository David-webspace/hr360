"""leave_attachments

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'leave_attachments',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('emp_id', sa.Integer(), nullable=True),
        sa.Column('request_id', sa.Integer(), nullable=True),
        sa.Column('original_name', sa.String(length=200), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('extracted', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['emp_id'], ['employees.id']),
        sa.ForeignKeyConstraint(['request_id'], ['leave_requests.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_leave_attachments_user_id', 'leave_attachments', ['user_id'])
    op.create_index('ix_leave_attachments_request_id', 'leave_attachments', ['request_id'])


def downgrade() -> None:
    op.drop_index('ix_leave_attachments_request_id', table_name='leave_attachments')
    op.drop_index('ix_leave_attachments_user_id', table_name='leave_attachments')
    op.drop_table('leave_attachments')
