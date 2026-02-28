"""Add metadata field to documents table

Revision ID: 002
Revises: 001
Create Date: 2024-12-11 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add extraction_metadata column to documents table
    op.add_column('documents', sa.Column('extraction_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    # Remove extraction_metadata column from documents table
    op.drop_column('documents', 'extraction_metadata')