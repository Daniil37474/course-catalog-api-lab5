"""Measure response-body bytes and SQL statements, excluding HTTP headers."""
import argparse
import asyncio
import json
from pathlib import Path

import httpx

MY_COURSES = '''query MyCourses($id: ID!) {
  student(id: $id) {
    name
    enrollments { id course { title credits level } }
  }
}'''


async def rest(client, student):
    first = await asyncio.gather(client.get(f'/students/{student}'),
                                 client.get(f'/students/{student}/enrollments'))
    for response in first:
        response.raise_for_status()
    second = await asyncio.gather(*(client.get('/courses/' + e['courseId'])
                                   for e in first[1].json()))
    for response in second:
        response.raise_for_status()
    return [*first, *second], 2


async def graphql(client, student):
    response = await client.post('/graphql', json={'query': MY_COURSES, 'variables': {'id': str(student)}})
    response.raise_for_status()
    body = response.json()
    if body.get('errors') or body.get('data', {}).get('student') is None:
        raise RuntimeError(body)
    return [response], 1


async def measure(api, student=2):
    rows = []
    async with httpx.AsyncClient(base_url=api, timeout=20) as client:
        for name, run in [('REST', rest), ('GraphQL', graphql)]:
            responses, rounds = await run(client, student)
            rows.append(dict(api=name, requests=len(responses), rounds=rounds,
                             bytes=sum(len(r.content) for r in responses),
                             sql_queries=sum(int(r.headers['x-sql-queries']) for r in responses)))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://localhost:8000')
    parser.add_argument('--student', type=int, default=2)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    rows = asyncio.run(measure(args.base_url, args.student))
    print(f"{'API':8} {'requests':9} {'rounds':7} {'bytes':8} SQL queries")
    for row in rows:
        print(f"{row['api']:8} {row['requests']:<9} {row['rounds']:<7} {row['bytes']:<8} {row['sql_queries']}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
