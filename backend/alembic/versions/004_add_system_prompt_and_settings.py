"""Add system_prompt to environments, cascade conversations, non-nullable environment_id on documents

Revision ID: 004
Revises: 003
Create Date: 2026-03-05 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add system_prompt and settings columns to environments
    op.add_column(
        'environments',
        sa.Column('system_prompt', sa.Text(), nullable=True),
    )
    op.add_column(
        'environments',
        sa.Column('settings', sa.dialects.postgresql.JSONB(), nullable=True),
    )

    # Add environment_id to conversations if not present
    # and add FK constraint with CASCADE delete
    try:
        op.add_column(
            'conversations',
            sa.Column(
                'environment_id',
                sa.dialects.postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
    except Exception:
        pass  # Column may already exist from app-level model

    # Ensure FK exists with CASCADE
    try:
        op.drop_constraint(
            'conversations_environment_id_fkey',
            'conversations',
            type_='foreignkey',
        )
    except Exception:
        pass

    op.create_foreign_key(
        'fk_conversations_environment_id',
        'conversations',
        'environments',
        ['environment_id'],
        ['id'],
        ondelete='CASCADE',
    )

    op.create_index(
        'idx_conversations_environment',
        'conversations',
        ['environment_id'],
        unique=False,
        if_not_exists=True,
    )

    # Create a default environment for orphan documents
    op.execute(
        """
        INSERT INTO environments (id, name, description, created_by, created_at, updated_at)
        VALUES (
            'a0000000-0000-0000-0000-000000000001',
            'default',
            'Default environment for previously unassigned documents',
            'system',
            now(),
            now()
        )
        ON CONFLICT (name) DO NOTHING
        """
    )

    # Assign orphan documents to the default environment
    op.execute(
        """
        UPDATE documents
        SET environment_id = 'a0000000-0000-0000-0000-000000000001'
        WHERE environment_id IS NULL
        """
    )

    # Make environment_id non-nullable
    op.alter_column(
        'documents',
        'environment_id',
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_index('idx_conversations_environment', table_name='conversations', if_exists=True)

    try:
        op.drop_constraint(
            'fk_conversations_environment_id',
            'conversations',
            type_='foreignkey',
        )
    except Exception:
        pass

    # Revert environment_id to nullable on documents
    op.alter_column(
        'documents',
        'environment_id',
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    op.drop_column('environments', 'settings')
    op.drop_column('environments', 'system_prompt')
