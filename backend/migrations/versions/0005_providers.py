"""Connection profiles without secrets; immutable routing configuration."""
from alembic import op
from sqlalchemy import Column,String,JSON
revision='0005'
down_revision='0004'


def upgrade():op.create_table('model_providers',Column('id',String,primary_key=True),Column('data',JSON,nullable=False))


def downgrade():raise RuntimeError('Restore backup instead of destroying provider history')
