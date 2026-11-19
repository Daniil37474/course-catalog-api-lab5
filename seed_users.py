"""Create local demo accounts with Argon2id hashes; never reset an existing password."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import SessionLocal
from models import Student, User
from security import password_hash

# Public demonstration credentials only. These are not deployment credentials.
DEMO_USERS = [
    ("admin@example.com", "admin-demo-password", "admin", None),
    ("aigerim@example.com", "aigerim-demo-pass", "student", "aigerim@example.com"),
    ("daniyar@example.com", "daniyar-demo-pass", "student", "daniyar@example.com"),
]


def seed_users(db: Session) -> None:
    for email, password, role, student_email in DEMO_USERS:
        if db.scalar(select(User).where(User.email == email)) is not None:
            continue
        student_id = None
        if student_email:
            student_id = db.scalar(select(Student.id).where(Student.email == student_email))
            if student_id is None:
                raise RuntimeError("Load seed.sql before creating demo accounts")
        db.add(User(email=email, password_hash=password_hash.hash(password),
                    role=role, student_id=student_id))
    db.commit()


if __name__ == "__main__":
    with SessionLocal() as db:
        seed_users(db)
    print("Demo accounts are ready (existing passwords were preserved).")
