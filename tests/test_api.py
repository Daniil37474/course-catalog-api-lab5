import unittest

from fastapi.testclient import TestClient
from pydantic import ValidationError

from data import COURSES, find_course, get_all_courses
from main import app, pagination
from models import Course


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def ids(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return [course["id"] for course in response.json()]

    def test_health(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Course Catalog API is running"})

    def test_default_order_and_fields(self):
        self.assertEqual(self.ids("/courses"), [
            "ai-integration", "modern-frontend", "web-security",
            "backend-fastapi", "databases-postgresql", "api-design",
        ])
        for course in self.client.get("/courses").json():
            self.assertEqual(set(course), {"id", "title", "description", "credits", "is_elective", "likes"})

    def test_elective_filter(self):
        self.assertEqual(self.ids("/courses?is_elective=true"), ["ai-integration", "api-design"])

    def test_required_filter(self):
        self.assertEqual(self.ids("/courses?is_elective=false"), [
            "modern-frontend", "web-security", "backend-fastapi", "databases-postgresql",
        ])

    def test_title_sort(self):
        self.assertEqual(self.ids("/courses?sort=title"), [
            "ai-integration", "api-design", "backend-fastapi",
            "modern-frontend", "databases-postgresql", "web-security",
        ])

    def test_pages(self):
        expected = [
            ["ai-integration", "modern-frontend"],
            ["web-security", "backend-fastapi"],
            ["databases-postgresql", "api-design"],
            [],
        ]
        for page, course_ids in enumerate(expected, start=1):
            with self.subTest(page=page):
                self.assertEqual(self.ids(f"/courses?page={page}&page_size=2"), course_ids)

    def test_filter_and_sort_before_pagination(self):
        self.assertEqual(self.ids("/courses?is_elective=false&sort=title&page=2&page_size=2"),
                         ["databases-postgresql", "web-security"])
        self.assertEqual(self.ids("/courses?is_elective=true&page=2&page_size=1"), ["api-design"])

    def test_single_course(self):
        response = self.client.get("/courses/web-security")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), find_course("web-security").model_dump())

    def test_missing_course(self):
        response = self.client.get("/courses/nope")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Course not found"})

    def test_search(self):
        for query, expected in [
            ("react", ["modern-frontend"]),
            ("ReAcT", ["modern-frontend"]),
            ("api", ["backend-fastapi", "api-design"]),
            ("unknown", []),
        ]:
            with self.subTest(query=query):
                self.assertEqual(self.ids(f"/courses?q={query}"), expected)
        self.assertEqual(self.ids("/courses?q="), self.ids("/courses"))
        self.assertEqual(self.ids("/courses?q=api&is_elective=true&sort=title&page_size=1"), ["api-design"])
        self.assertEqual(self.ids("/courses?q=api&sort=title&page=2&page_size=1"), ["backend-fastapi"])

    def test_invalid_query_parameters(self):
        for query in ["sort=banana", "page=0", "page=-1", "page_size=0",
                      "page_size=1000", "page=abc", "page=1.5", "is_elective=banana"]:
            with self.subTest(query=query):
                self.assertEqual(self.client.get(f"/courses?{query}").status_code, 422)
        self.assertEqual(len(self.ids("/courses?page_size=100")), 6)

    def test_pagination_dependency_is_used(self):
        app.dependency_overrides[pagination] = lambda: {"offset": 1, "limit": 1}
        try:
            self.assertEqual(self.ids("/courses"), ["modern-frontend"])
        finally:
            app.dependency_overrides.clear()

    def test_model_defaults_and_validation(self):
        course = Course(id="x", title="t", description="d", credits="5")
        self.assertEqual(course.credits, 5)
        self.assertFalse(course.is_elective)
        self.assertEqual(course.likes, 0)
        with self.assertRaises(ValidationError):
            Course(id="x", title="t", description="d", credits="five")

    def test_data_helpers_and_request_isolation(self):
        before = [course.model_dump() for course in COURSES]
        copied = get_all_courses()
        self.assertIsNot(copied, COURSES)
        copied.pop()
        self.client.get("/courses?sort=title&is_elective=true&page_size=1")
        self.assertEqual([course.model_dump() for course in COURSES], before)
        self.assertIsNone(find_course("nope"))
        self.assertEqual(len(COURSES), 6)

    def test_documentation_and_schema(self):
        for path in ["/docs", "/redoc", "/openapi.json"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        schema = self.client.get("/openapi.json").json()
        self.assertEqual(set(schema["paths"]), {"/", "/courses", "/courses/{course_id}"})
        self.assertTrue(all(set(path) == {"get"} for path in schema["paths"].values()))
        course = schema["components"]["schemas"]["Course"]
        self.assertEqual(set(course["required"]), {"id", "title", "description", "credits"})
        self.assertFalse(course["properties"]["is_elective"]["default"])
        self.assertEqual(course["properties"]["likes"]["default"], 0)
        params = {p["name"]: p["schema"] for p in schema["paths"]["/courses"]["get"]["parameters"]}
        self.assertEqual(set(params), {"page", "page_size", "is_elective", "sort", "q"})
        self.assertEqual(params["sort"]["enum"], ["popular", "title"])
        self.assertEqual(params["page"]["minimum"], 1)
        self.assertEqual(params["page_size"]["maximum"], 100)


if __name__ == "__main__":
    unittest.main()
