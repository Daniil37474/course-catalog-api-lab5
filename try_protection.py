import argparse
import httpx

CYCLE = 'query Cycle { student(id: 2) { enrollments { student { enrollments { student { enrollments { id } } } } } } }'
ALIASES = '{ ' + ' '.join(f'a{i}: course(id: "api-design") {{ title }}' for i in range(12)) + ' }'
CASES = [
    ('depth 6', CYCLE, 'exceeds maximum operation depth'),
    ('12 aliases', ALIASES, '12 aliases found. Allowed: 10'),
    ('limit -1', '{ courses(limit: -1) { id } }', 'limit must be between 1 and 100'),
    ('id abc', '{ student(id: "abc") { name } }', "Invalid ID: 'abc'"),
    ('id 20 digits', '{ student(id: "99999999999999999999") { name } }', 'Unexpected error.'),
    ('introspection', '{ __schema { queryType { name } } }', None),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://localhost:8000')
    parser.add_argument('--introspection-off', action='store_true')
    args = parser.parse_args()
    failed = 0
    with httpx.Client(base_url=args.base_url, timeout=15) as client:
        for title, query, expected in CASES:
            if title == 'introspection' and args.introspection_off:
                expected = 'introspection has been disabled'
            response = client.post('/graphql', json={'query': query})
            body = response.json()
            messages = '; '.join(e['message'] for e in body.get('errors', []))
            ok = response.status_code == 200 and (expected in messages if expected else not messages and bool(body.get('data')))
            failed += not ok
            print(f"{'ok' if ok else 'FAIL':4} {title:17} {response.status_code} {messages or 'data, no errors'}")
    return int(failed > 0)


if __name__ == '__main__':
    raise SystemExit(main())
