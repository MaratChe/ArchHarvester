"""Local model output retention and independent semantic index generations."""
from alembic import op
from sqlalchemy import Column, String, Float, JSON
revision='0004'
down_revision='0003'


def upgrade():
    op.create_table('search_indexes',Column('id',String,primary_key=True),Column('data',JSON,nullable=False))
    op.create_table('search_vectors',Column('id',String,primary_key=True),Column('index_id',String,nullable=False),Column('data',JSON,nullable=False))
    op.create_index('ix_vectors_generation','search_vectors',['index_id'])
    op.create_table('llm_outputs',Column('id',String,primary_key=True),Column('expires',Float,nullable=False),Column('data',JSON,nullable=False))


def downgrade():raise RuntimeError('Restore backup instead of dropping model history')
