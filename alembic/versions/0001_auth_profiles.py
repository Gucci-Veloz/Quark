"""users, api_keys, profiles

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(150), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("scopes", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("scopes", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])
    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "key", name="uq_profiles_tenant_key"),
    )
    op.create_index("ix_profiles_tenant_id", "profiles", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("profiles")
    op.drop_table("api_keys")
    op.drop_table("users")
