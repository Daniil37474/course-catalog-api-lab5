import os
from pathlib import Path
import subprocess
import sys

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

# Never run destructive seed operations against the application's database.
TEST_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_URL or not (make_url(TEST_URL).database.endswith("_test")
                        or make_url(TEST_URL).query.get("options") == "-csearch_path=lab9_test"):
    raise RuntimeError("Set TEST_DATABASE_URL to a dedicated _test database or the isolated lab9_test schema")
os.environ["DATABASE_URL"] = TEST_URL
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import get_db
from main import app
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def test_engine():
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, check=True)
    url = make_url(TEST_URL)
    with psycopg.connect(url.set(drivername="postgresql").render_as_string(hide_password=False)) as conn:
        conn.execute((root / "seed.sql").read_text(encoding="utf-8"))
    engine = create_engine(TEST_URL)
    from seed_users import seed_users
    with Session(engine) as db:
        seed_users(db)
    yield engine
    engine.dispose()


@pytest.fixture
def session(test_engine):
    with test_engine.connect() as conn:
        outer = conn.begin()
        with Session(bind=conn, join_transaction_mode="create_savepoint") as db:
            yield db
        outer.rollback()


@pytest.fixture
def client(session):
    def override_db():
        yield session
    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(client, session):
    from sqlalchemy import select
    from models import User
    from security import create_access_token
    user = session.scalar(select(User).where(User.email == "admin@example.com"))
    client.headers["Authorization"] = "Bearer " + create_access_token(user.id)
    return client
