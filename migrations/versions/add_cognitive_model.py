"""add cognitive_model to user, evolution fields to insight

Revision ID: add_cognitive_model
Revises: 1c25aef35b84
Create Date: 2026-06-15 23:15:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_cognitive_model'
down_revision = '1c25aef35b84'
branch_labels = None
depends_on = None


def upgrade():
    # Add cognitive_model column to users table
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cognitive_model', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))

    # Add evolution fields to insights table
    with op.batch_alter_table('insights', schema=None) as batch_op:
        batch_op.add_column(sa.Column('evolution_stages', sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch_op.add_column(sa.Column('hypotheses', sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch_op.add_column(sa.Column('triggers', sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch_op.add_column(sa.Column('affected_areas', sa.JSON(), nullable=False, server_default=sa.text("'[]'")))


def downgrade():
    with op.batch_alter_table('insights', schema=None) as batch_op:
        batch_op.drop_column('affected_areas')
        batch_op.drop_column('triggers')
        batch_op.drop_column('hypotheses')
        batch_op.drop_column('evolution_stages')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('cognitive_model')
