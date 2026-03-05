"""Denormalize environment_id on document_chunks for faster vector search

Revision ID: 005
Revises: 004
Create Date: 2026-03-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add environment_id column (nullable first for backfill)
    op.add_column(
        'document_chunks',
        sa.Column(
            'environment_id',
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    # Backfill from documents table
    op.execute(
        """
        UPDATE document_chunks dc
        SET environment_id = d.environment_id
        FROM documents d
        WHERE dc.document_id = d.id
        """
    )

    # Make non-nullable after backfill
    op.alter_column(
        'document_chunks',
        'environment_id',
        nullable=False,
    )

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_document_chunks_environment_id',
        'document_chunks',
        'environments',
        ['environment_id'],
        ['id'],
    )

    # Add index for environment-scoped vector search
    op.create_index(
        'idx_document_chunks_environment',
        'document_chunks',
        ['environment_id'],
    )


def downgrade() -> None:
    op.drop_index('idx_document_chunks_environment', table_name='document_chunks')
    op.drop_constraint(
        'fk_document_chunks_environment_id',
        'document_chunks',
        type_='foreignkey',
    )
    op.drop_column('document_chunks', 'environment_id')
