import unittest

from fastapi.testclient import TestClient
from data import COURSES
from main import app, ENROLLMENTS
from models import EnrollmentIn


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.likes = [course.likes for course in COURSES]
        self.enrollments = ENROLLMENTS.copy()
        ENROLLMENTS.clear()

    def tearDown(self):
        for course, likes in zip(COURSES, self.likes):
            course.likes = likes
        ENROLLMENTS[:] = self.enrollments
        self.client.close()

    def test_cors_origins_and_preflight(self):
        for origin, allowed in [("http://localhost:3000", True),
                                ("http://evil.example", False),
                                ("http://localhost:3000/", False),
                                ("http://127.0.0.1:3000", False)]:
            with self.subTest(origin=origin):
                response = self.client.get("/courses", headers={"Origin": origin})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers.get("access-control-allow-origin"), origin if allowed else None)
                preflight = self.client.options("/enrollments", headers={
                    "Origin": origin, "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                })
                self.assertEqual(preflight.status_code, 200 if allowed else 400)
                if allowed:
                    self.assertIn("POST", preflight.headers["access-control-allow-methods"])
                    self.assertEqual(preflight.headers["access-control-max-age"], "600")

    def test_like_updates_server_and_missing_course(self):
        old = self.client.get("/courses/web-security").json()["likes"]
        for value in [old + 1, old + 2]:
            response = self.client.post("/courses/web-security/like")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["likes"], value)
            self.assertIn("isElective", response.json())
        self.assertEqual(self.client.get("/courses/web-security").json()["likes"], old + 2)
        self.assertEqual(self.client.post("/courses/nope/like").status_code, 404)

    def test_enrollment_contract_validation_and_storage(self):
        body = {"courseId": "web-security", "studentName": "Aigerim"}
        created = self.client.post("/enrollments", json=body)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json(), {**body, "id": 1})
        self.assertEqual(self.client.get("/enrollments").json(), [{**body, "id": 1}])
        rejected = self.client.post("/enrollments", json={**body, "studentName": "A"})
        self.assertEqual(rejected.status_code, 422)
        self.assertEqual(rejected.json()["detail"][0]["loc"], ["body", "studentName"])
        self.assertEqual(self.client.post("/enrollments", json={**body, "courseId": "nope"}).status_code, 404)
        self.assertEqual(len(ENROLLMENTS), 1)
        self.assertEqual(self.client.post("/enrollments", json=body).json()["id"], 2)

    def test_aliases_keep_python_names_and_query_parameters(self):
        snake = EnrollmentIn(course_id="web-security", student_name="Aigerim")
        camel = EnrollmentIn(courseId="web-security", studentName="Aigerim")
        self.assertEqual(snake, camel)
        self.assertEqual(len(self.client.get("/courses?is_elective=true").json()), 2)
        self.assertEqual(len(self.client.get("/courses?isElective=true").json()), 6)

    def test_text_body_is_not_json(self):
        response = self.client.post("/enrollments", content='{"courseId":"web-security","studentName":"Aigerim"}',
                                    headers={"Content-Type": "text/plain"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(ENROLLMENTS, [])


if __name__ == "__main__":
    unittest.main()
