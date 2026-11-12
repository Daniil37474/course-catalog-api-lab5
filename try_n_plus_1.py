import argparse
import httpx

QUERIES = [
    ('students -> enrollments -> course', '{ students { name enrollments { course { title } } } }', 'students'),
    ('enrollments -> course, student', '{ enrollments { course { title } student { name } } }', 'enrollments'),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://localhost:8000')
    parser.add_argument('--expect', type=int, default=3)
    args = parser.parse_args()
    failed = 0
    with httpx.Client(base_url=args.base_url, timeout=15) as client:
        for title, query, field in QUERIES:
            response = client.post('/graphql', json={'query': query})
            response.raise_for_status()
            body = response.json()
            if body.get('errors'):
                print('FAIL', body['errors'])
                failed += 1
                continue
            count = int(response.headers['x-sql-queries'])
            print(f"{title:36} rows: {len(body['data'][field])} SQL queries: {count}")
            failed += count != args.expect
    return int(failed > 0)


if __name__ == '__main__':
    raise SystemExit(main())
