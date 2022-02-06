"""empty message

Revision ID: a2438fe06b96
Revises: 0fcf9d387a0f
Create Date: 2022-01-20 18:08:17.730534

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2438fe06b96'
down_revision = '0fcf9d387a0f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('location', sa.Column('dispatch_user_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'location', 'dispatch_user', ['dispatch_user_id'], ['id'], referent_schema='dispatch_core')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'location', type_='foreignkey')
    op.drop_column('location', 'dispatch_user_id')
    # ### end Alembic commands ###