import pytest
from sqlalchemy import select
from models import Course


def ids(client, url):
    r = client.get(url)
    assert r.status_code == 200
    return [c["id"] for c in r.json()]


def test_health_docs_and_contract(client):
    assert client.get("/").json() == {"message": "Course Catalog API is running"}
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert sum(len(v) for v in paths.values()) == 8
    course = client.get("/courses/api-design").json()
    assert set(course) == {"id", "title", "description", "credits", "isElective", "likes", "level"}
    assert course["level"] == "beginner"


def test_filters_pages_and_search(client):
    assert ids(client, "/courses?is_elective=false&page_size=3") == ["modern-frontend", "web-security", "backend-fastapi"]
    assert ids(client, "/courses?is_elective=false&page_size=3&page=2") == ["databases-postgresql"]
    assert ids(client, "/courses?level=beginner") == ["ai-integration", "api-design"]
    assert ids(client, "/courses?level=advanced") == []
    assert ids(client, "/courses?level=beginner&is_elective=false") == []
    assert ids(client, "/courses?q=ReAcT") == ["modern-frontend"]
    assert ids(client, "/courses?q=api&sort=title&page=2&page_size=1") == ["backend-fastapi"]
    assert ids(client, "/courses?q=%25") == []  # Literal %, not an SQL wildcard.
    assert ids(client, "/courses?sort=title") == ["ai-integration", "api-design", "backend-fastapi", "modern-frontend", "databases-postgresql", "web-security"]


@pytest.mark.parametrize("query", ["sort=banana", "page=0", "page=-1", "page_size=0", "page_size=101", "page=abc", "is_elective=banana"])
def test_invalid_query(client, query):
    assert client.get("/courses?" + query).status_code == 422


def test_stable_tie_order(client, session):
    a = session.get(Course, "api-design")
    b = session.get(Course, "ai-integration")
    a.likes = b.likes = 100
    session.flush()
    assert ids(client, "/courses?page_size=1") == ["ai-integration"]
    assert ids(client, "/courses?page_size=1&page=2") == ["api-design"]


def test_like_and_missing_course(client, session):
    assert client.get("/courses/nope").status_code == 404
    assert client.post("/courses/nope/like").status_code == 404
    for expected in (12, 13):
        response = client.post("/courses/api-design/like")
        assert response.status_code == 200
        assert response.json()["likes"] == expected
    assert session.scalar(select(Course.likes).where(Course.id == "api-design")) == 13


def test_stats_include_zero_courses(client):
    stats = client.get("/stats/courses").json()
    assert [(s["courseId"], s["enrolled"]) for s in stats] == [
        ("ai-integration", 3), ("modern-frontend", 2), ("backend-fastapi", 1),
        ("api-design", 0), ("databases-postgresql", 0), ("web-security", 0),
    ]
    rows = client.get("/enrollments").json()
    assert sum(s["enrolled"] for s in stats) == len(rows) == 6
    assert rows[0]["studentName"] == "Aigerim Sadykova"
    assert rows[0]["courseTitle"] == "Modern Frontend: React & Next.js"
    assert "enrolledAt" in rows[0]
