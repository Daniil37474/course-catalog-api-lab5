"""Add accounts without changing existing catalog data."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("student_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("role IN ('student', 'admin')", name=op.f("users_role_check")),
        sa.CheckConstraint(
            "(role = 'student' AND student_id IS NOT NULL) OR "
            "(role = 'admin' AND student_id IS NULL)", name=op.f("users_profile_check"),
        ),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"],
                                name="users_student_id_fkey", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="users_pkey"),
        sa.UniqueConstraint("email", name="users_email_key"),
        sa.UniqueConstraint("student_id", name="users_student_id_key"),
    )


def downgrade() -> None:
    op.drop_table("users")
