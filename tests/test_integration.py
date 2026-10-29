from datetime import datetime
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from models import Course, Enrollment, Student
from main import CONSTRAINT_ERRORS
from try_errors import CASES


@pytest.mark.parametrize("title,path,body,status", CASES)
def test_constraint_responses(client, title, path, body, status):
    r = client.post(path, json=body)
    assert r.status_code == status, r.text
    assert client.get("/courses").status_code == 200  # Session recovered after rollback.


def test_create_student_enroll_and_join(client):
    r = client.post("/students", json={"name": "Nurlan Abenov", "email": "nurlan@example.com"})
    assert r.status_code == 201
    sid = r.json()["id"]
    body = {"courseId": "web-security", "studentId": sid}
    e = client.post("/enrollments", json=body)
    assert e.status_code == 201
    assert datetime.fromisoformat(e.json()["enrolledAt"]).tzinfo is not None
    rows = client.get("/enrollments").json()
    row = next(x for x in rows if x["id"] == e.json()["id"])
    assert row["studentName"] == "Nurlan Abenov"
    assert row["courseTitle"] == "Web Security Essentials"
    assert client.post("/enrollments", json=body).status_code == 409


def test_old_contract_and_invalid_email(client):
    assert client.post("/enrollments", json={"courseId": "web-security", "studentName": "Aigerim"}).status_code == 422
    assert client.post("/students", json={"name": "Valid Name", "email": "not-an-email"}).status_code == 422
    assert client.post("/enrollments", content='{}', headers={"Content-Type": "text/plain"}).status_code == 422


def test_unknown_constraint_remains_server_error(client, monkeypatch):
    monkeypatch.delitem(CONSTRAINT_ERRORS, "students_email_key")
    r = client.post("/students", json={"name": "Duplicate", "email": "aigerim@example.com"})
    assert r.status_code == 500
    assert client.get("/courses").status_code == 200


def test_loaded_relationships_use_database_delete_rules(session):
    student = session.get(Student, 2)
    assert len(student.enrollments) == 3
    session.delete(student)
    session.flush()
    assert session.scalar(select(func.count()).select_from(Enrollment)) == 3
    course = session.get(Course, "modern-frontend")
    assert len(course.enrollments) == 1
    session.delete(course)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_cors(client):
    for origin, allowed in [("http://localhost:3000", True), ("http://evil.example", False)]:
        r = client.options("/enrollments", headers={"Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
        assert r.status_code == (200 if allowed else 400)
        assert r.headers.get("access-control-allow-origin") == (origin if allowed else None)
