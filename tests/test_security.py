"""Lab 9 regression tests: authentication, BOLA, field access, token validation."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys

import jwt
import pytest
from sqlalchemy import select

from config import settings
from models import User
from security import ALGORITHM, ISSUER, create_access_token, password_hash


def headers(session, email="aigerim@example.com"):
    user = session.scalar(select(User).where(User.email == email))
    return {"Authorization": "Bearer " + create_access_token(user.id)}


@pytest.mark.parametrize("email", ["nobody@example.com", "aigerim@example.com"])
def test_login_failure_is_generic(client, email):
    r = client.post("/auth/login", data={"username": email, "password": "wrong-password-123"})
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["detail"] == "Incorrect email or password"


def test_login_and_openapi(client):
    r = client.post("/auth/login", data={
        "username": " AIGERIM@example.com ", "password": "aigerim-demo-pass",
    })
    assert r.status_code == 200
    assert set(r.json()) == {"access_token", "token_type", "expires_in"}
    assert r.json()["expires_in"] == 900
    me = client.get("/me", headers={"Authorization": "Bearer " + r.json()["access_token"]})
    assert me.json()["studentId"] == 1
    assert "password_hash" not in me.text and "passwordHash" not in me.text
    spec = client.get("/openapi.json").json()
    flow = spec["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]["password"]
    assert flow["tokenUrl"] == "auth/login"
    assert client.post("/auth/login", data={"username": "aigerim@example.com"}).status_code == 422


@pytest.mark.parametrize("actor", ["anonymous", "student", "admin"])
@pytest.mark.parametrize("method,path,body,expected", [
    ("GET", "/courses", None, [200, 200, 200]),
    ("GET", "/me", None, [401, 200, 200]),
    ("GET", "/enrollments", None, [401, 403, 200]),
    ("POST", "/enrollments", {"courseId": "api-design", "studentId": 1}, [401, 201, 201]),
    ("POST", "/enrollments", {"courseId": "web-security", "studentId": 2}, [401, 403, 201]),
])
def test_permission_matrix(client, session, actor, method, path, body, expected):
    auth = {} if actor == "anonymous" else headers(
        session, "admin@example.com" if actor == "admin" else "aigerim@example.com")
    r = client.request(method, path, json=body, headers=auth)
    assert r.status_code == expected[["anonymous", "student", "admin"].index(actor)], r.text
    if r.status_code == 401:
        assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("path", ["/students/2", "/students/2/enrollments"])
def test_rest_does_not_leak_other_profile(client, session, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers(session)).status_code == 403
    assert client.get(path, headers=headers(session, "admin@example.com")).status_code == 200


@pytest.mark.parametrize("defect", [
    "expired", "foreign-key", "no-exp", "no-sub", "no-iss", "no-iat", "wrong-issuer",
    "none", "numeric-sub", "text-sub", "huge-sub", "negative-sub", "zero-sub", "garbage",
])
def test_bad_tokens_are_401(client, session, defect):
    user = session.scalar(select(User).where(User.email == "aigerim@example.com"))
    now = datetime.now(timezone.utc)
    claims = {"sub": str(user.id), "iss": ISSUER, "iat": now, "exp": now + timedelta(minutes=15)}
    key = settings.secret_key
    algorithm = ALGORITHM
    if defect == "expired":
        claims["exp"] = now - timedelta(seconds=1)
    elif defect.startswith("no-"):
        claims.pop(defect[3:])
    elif defect == "foreign-key":
        key = "other-key-" * 8
    elif defect == "wrong-issuer":
        claims["iss"] = "another-service"
    elif defect == "none":
        key, algorithm = "", "none"
    elif defect == "numeric-sub":
        claims["sub"] = user.id
    elif defect == "text-sub":
        claims["sub"] = "abc"
    elif defect == "huge-sub":
        claims["sub"] = "9999999999999999999999999999"
    elif defect == "negative-sub":
        claims["sub"] = "-1"
    elif defect == "zero-sub":
        claims["sub"] = "0"
    token = "forged.token.value" if defect == "garbage" else jwt.encode(claims, key, algorithm=algorithm)
    for path in ["/me", "/courses", "/graphql"]:
        r = client.get(path, headers={"Authorization": "Bearer " + token})
        assert r.status_code == 401, r.text
        assert r.json()["detail"] == "Invalid or expired token"


def test_role_is_read_from_database_with_same_token(client, session):
    auth = headers(session)
    assert client.get("/enrollments", headers=auth).status_code == 403
    user = session.scalar(select(User).where(User.email == "aigerim@example.com"))
    user.role, user.student_id = "admin", None
    session.flush()
    assert client.get("/enrollments", headers=auth).status_code == 200


def test_deleted_account_rejects_old_token(client, session):
    auth = headers(session, "admin@example.com")
    user = session.scalar(select(User).where(User.email == "admin@example.com"))
    session.delete(user)
    session.flush()
    assert client.get("/me", headers=auth).status_code == 401


def gql(client, query, auth=None):
    return client.post("/graphql", json={"query": query}, headers=auth or {})


def test_graphql_me_and_students(client, session):
    r = gql(client, "{ me { email role } }")
    assert r.status_code == 200 and r.json()["errors"][0]["message"] == "Authentication required"
    for auth, allowed in [({}, False), (headers(session), False),
                          (headers(session, "admin@example.com"), True)]:
        body = gql(client, "{ students { name email } }", auth).json()
        assert bool(body.get("errors")) is not allowed
    own = gql(client, "{ me { email role studentId } }", headers(session)).json()
    assert own["data"]["me"]["studentId"] == 1


def test_graphql_email_is_protected_on_all_paths(client, session):
    auth = headers(session)
    own = gql(client, '{ student(id: "1") { name email } }', auth).json()
    assert own["data"]["student"]["email"] == "aigerim@example.com"
    for auth in [{}, headers(session)]:
        body = gql(client, '{ student(id: "2") { name email } }', auth).json()
        assert body["data"]["student"] == {"name": "Daniyar Bekov", "email": None}
        assert body["errors"][0]["path"] == ["student", "email"]
    # The root list and the course->enrollments path both reach the same protected field.
    for query in ["{ enrollments { student { id name email } } }",
                  '{ course(id: "modern-frontend") { enrollments { student { id name email } } } }']:
        body = gql(client, query, headers(session)).json()
        assert body.get("errors")
        assert "daniyar@example.com" not in str(body)
        assert "aigerim@example.com" in str(body)
    body = gql(client, '{ student(id: "2") { email } }', headers(session, "admin@example.com")).json()
    assert body["data"]["student"]["email"] == "daniyar@example.com"


def test_graphql_enroll_owner_check(client, session):
    query = 'mutation { enroll(input: {courseId: "api-design", studentId: "2"}) { enrollment { id } userErrors { code } } }'
    assert gql(client, query).json().get("errors")
    assert gql(client, query, headers(session)).json()["errors"][0]["message"] == "You can enroll only yourself"
    assert gql(client, query, headers(session, "admin@example.com")).json()["data"]["enroll"]["enrollment"]
    own = query.replace('studentId: "2"', 'studentId: "1"')
    assert gql(client, own, headers(session)).json()["data"]["enroll"]["enrollment"]


def test_argon_hashes_and_salts(session):
    user = session.scalar(select(User).where(User.email == "aigerim@example.com"))
    assert user.password_hash.startswith("$argon2id$")
    assert password_hash.verify("aigerim-demo-pass", user.password_hash)
    assert password_hash.hash("same-password-value") != password_hash.hash("same-password-value")


@pytest.mark.parametrize("secret", [None, "short"])
def test_key_is_required_and_has_minimum_length(tmp_path, secret):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    env.pop("SECRET_KEY", None)
    if secret is not None:
        env["SECRET_KEY"] = secret
    proc = subprocess.run([sys.executable, "-c", "import config"], cwd=tmp_path,
                          env=env, capture_output=True, text=True)
    assert proc.returncode != 0 and "secret_key" in proc.stderr


def test_token_survives_browser_logout_until_expiry(client, session):
    # The frontend deletes only its cookie. A separately copied bearer token still works.
    auth = headers(session)
    assert client.get("/me", headers=auth).status_code == 200
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers=auth).status_code == 200
