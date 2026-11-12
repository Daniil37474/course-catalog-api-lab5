"""Read-only checks against the seed data; exit nonzero on failure."""
import argparse
import httpx


def enroll(course_id, student_id):
    return ('mutation { enroll(input: {courseId: "' + course_id +
            '", studentId: "' + student_id + '"}) '
            '{ enrollment { id } userErrors { code } } }')


CASES = [
    ("courses(limit: 2)", "{ courses(limit: 2) { id } }",
     lambda d: ','.join(c['id'] for c in d['data']['courses']), 'ai-integration,modern-frontend'),
    ("course", '{ course(id: "api-design") { title } }',
     lambda d: d['data']['course']['title'], 'API Design: REST vs GraphQL'),
    ("missing course", '{ course(id: "nope") { title } }',
     lambda d: d['data']['course'], None),
    ("student enrollments", '{ student(id: 2) { enrollments { course { id } } } }',
     lambda d: len(d['data']['student']['enrollments']), 3),
    ("duplicate enrollment", enroll('ai-integration', '3'),
     lambda d: d['data']['enroll']['userErrors'][0]['code'], 'ALREADY_ENROLLED'),
    ("unknown course", enroll('nope', '3'),
     lambda d: d['data']['enroll']['userErrors'][0]['code'], 'COURSE_NOT_FOUND'),
    ("unknown student", enroll('web-security', '999'),
     lambda d: d['data']['enroll']['userErrors'][0]['code'], 'STUDENT_NOT_FOUND'),
    ("unknown field", '{ course(id: "api-design") { titel } }',
     lambda d: d['errors'][0]['message'].split('. Did you')[0],
     "Cannot query field 'titel' on type 'Course'"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://localhost:8000')
    args = parser.parse_args()
    failed = 0
    with httpx.Client(base_url=args.base_url, timeout=15) as client:
        for title, query, pick, expected in CASES:
            response = client.post('/graphql', json={'query': query})
            try:
                actual = pick(response.json())
                ok = response.status_code == 200 and actual == expected
            except (KeyError, IndexError, TypeError, ValueError):
                actual, ok = response.text, False
            failed += not ok
            print(f"{'ok' if ok else 'FAIL':4} {title:25} {actual}")
    print(f'{len(CASES)-failed} of {len(CASES)} as expected')
    return int(failed > 0)


if __name__ == '__main__':
    raise SystemExit(main())
