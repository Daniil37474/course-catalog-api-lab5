"""On the protected server this request must not change any likes."""
import argparse
import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://localhost:8000')
    args = parser.parse_args()
    operations = ' '.join(f'a{i}: likeCourse(id: "api-design") {{ course {{ likes }} }}' for i in range(12))
    with httpx.Client(base_url=args.base_url, timeout=15) as client:
        before = client.get('/courses/api-design').json()['likes']
        response = client.post('/graphql', json={'query': 'mutation { ' + operations + ' }'})
        body = response.json()
        after = client.get('/courses/api-design').json()['likes']
    print('HTTP status:', response.status_code)
    print('Response:', body)
    print('SQL queries:', response.headers.get('x-sql-queries'))
    print('Likes before / after:', before, after)
    ok = (response.status_code == 200 and bool(body.get('errors'))
          and '12 aliases found' in body['errors'][0]['message']
          and response.headers.get('x-sql-queries') == '0' and before == after)
    return int(not ok)


if __name__ == '__main__':
    raise SystemExit(main())
