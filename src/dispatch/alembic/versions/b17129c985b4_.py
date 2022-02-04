"""Added zulip support for any organization.

Revision ID: b17129c985b4
Revises: 390951c2a6ef
Create Date: 2021-12-06 17:50:27.270331

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b17129c985b4'
down_revision = '390951c2a6ef'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('organization', sa.Column('zulip_is_active', sa.Boolean(), nullable=True))
    op.add_column('organization', sa.Column('zulip_password', sa.LargeBinary(), nullable=True))
    op.add_column('organization', sa.Column('zulip_site', sa.String(), nullable=True))
    op.add_column('organization', sa.Column('zulip_user_name', sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('organization', 'zulip_user_name')
    op.drop_column('organization', 'zulip_site')
    op.drop_column('organization', 'zulip_password')
    op.drop_column('organization', 'zulip_is_active')
    # ### end Alembic commands ###
