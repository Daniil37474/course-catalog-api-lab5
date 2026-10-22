# Course Catalog API

FastAPI backend for Labs 4-5. It returns six courses, supports filtering and sorting, and handles likes and course enrollment. Frontend: https://github.com/Daniil37474/course-catalog-lab5.

## Setup

Requires Python 3.10 or newer. Run from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\fastapi.exe dev main.py --port 8000
```

On macOS/Linux: `python3 -m venv .venv`, `source .venv/bin/activate`, `pip install -r requirements.txt`, `fastapi dev main.py --port 8000`.

API: http://localhost:8000. Swagger UI: http://localhost:8000/docs. `/redoc` and `/openapi.json` are also available. Run the frontend at **http://localhost:3000**.

## Routes and data contract

| Method and path | Result |
| --- | --- |
| `GET /` | 200, API status message |
| `GET /courses` | Six courses, sorted by likes in descending order |
| `GET /courses/{course_id}` | 200 with a course; 404 for an unknown ID |
| `POST /courses/{course_id}/like` | 200 with the updated course; 404 for an unknown ID |
| `POST /enrollments` | 201 with a new enrollment ID; 404 for an unknown course; 422 for invalid fields |
| `GET /enrollments` | 200 with the enrollment list |

Lab 4 query parameters are preserved: `is_elective`, `q`, `sort=popular|title`, `page` starting at 1, and `page_size` from 1 to 100. Filtering and sorting happen before pagination. `?is_elective=true` returns two courses. The unknown parameter `?isElective=true` is ignored and returns all six.

Python models use snake_case. The shared `CamelModel` sets `alias_generator=to_camel`, `validate_by_name=True`, and `validate_by_alias=True`; JSON and OpenAPI use camelCase. Requires Pydantic 2.11+.

Enrollment request body:

```json
{"courseId":"web-security","studentName":"Aigerim"}
```

Response with status 201:

```json
{"courseId":"web-security","studentName":"Aigerim","id":1}
```

Names shorter than two characters are rejected with status 422 and `loc: ["body", "studentName"]`. The request must use `Content-Type: application/json`.

## CORS

Only `http://localhost:3000` is allowed, without a trailing slash. All methods and headers are allowed. The API returns `Access-Control-Allow-Origin` for the allowed origin and omits it for other origins. JSON POST preflight returns 200 and `Access-Control-Max-Age: 600`.

```powershell
curl.exe -i -X OPTIONS http://localhost:8000/enrollments -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: content-type"
```

CORS restricts browser JavaScript from reading a response; it does not prevent the server from processing a simple request. Server Components call the API directly, without browser CORS checks.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests cover the original routes, search, filtering, sorting, pagination, models, OpenAPI, CORS, preflight, likes, enrollment, status codes 200/201/404/422, and both field naming conventions. Data changes are restored after each scenario.

Data is stored in memory. Restarting the server resets likes, enrollments, and enrollment numbering. This is a single-process educational implementation without persistent storage or authentication.

## Lab 5 changes

- Allowed the `http://localhost:3000` origin so the browser frontend can read responses from the separate API.
- Added `CamelModel` to match JSON field names to TypeScript while preserving Python names and existing query parameters.
- `POST /courses/{course_id}/like` returns the updated course, for example `{"id":"web-security","title":"Web Security Essentials","description":"JWT/OAuth2, defending against XSS, CSRF, SQL injection.","credits":4,"isElective":false,"likes":22}`.
- `POST /enrollments` returns 201 and `{"courseId":"web-security","studentName":"Aigerim","id":1}`.
- `GET /enrollments` returns the created enrollments, for example `[{"courseId":"web-security","studentName":"Aigerim","id":1}]`.
