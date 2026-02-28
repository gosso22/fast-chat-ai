"""Add environments and user roles tables

Revision ID: 003
Revises: 002
Create Date: 2024-12-12 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create environments table for isolated knowledge bases
    op.create_table(
        'environments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_environments_name'),
    )
    op.create_index(op.f('ix_environments_id'), 'environments', ['id'], unique=False)

    # Create user_roles table
    op.create_table(
        'user_roles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('environment_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'chat_user')", name='check_user_role'),
        sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'environment_id', name='uq_user_environment'),
    )
    op.create_index(op.f('ix_user_roles_id'), 'user_roles', ['id'], unique=False)
    op.create_index(op.f('ix_user_roles_user_id'), 'user_roles', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_roles_environment_id'), 'user_roles', ['environment_id'], unique=False)

    # Add environment_id foreign key to documents table
    op.add_column(
        'documents',
        sa.Column('environment_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_documents_environment_id',
        'documents',
        'environments',
        ['environment_id'],
        ['id'],
    )
    op.create_index('idx_documents_environment', 'documents', ['environment_id'], unique=False)


def downgrade() -> None:
    # Remove environment_id from documents
    op.drop_index('idx_documents_environment', table_name='documents')
    op.drop_constraint('fk_documents_environment_id', 'documents', type_='foreignkey')
    op.drop_column('documents', 'environment_id')

    # Drop user_roles table
    op.drop_index(op.f('ix_user_roles_environment_id'), table_name='user_roles')
    op.drop_index(op.f('ix_user_roles_user_id'), table_name='user_roles')
    op.drop_index(op.f('ix_user_roles_id'), table_name='user_roles')
    op.drop_table('user_roles')

    # Drop environments table
    op.drop_index(op.f('ix_environments_id'), table_name='environments')
    op.drop_table('environments')
