# course-catalog-api

Backend of the course catalog: FastAPI, SQLAlchemy 2.1, PostgreSQL, Alembic and GraphQL on Strawberry as a second entrance (Labs 4–8, "Advanced Web Technologies").

## How to run

You need Python 3.11 or newer and PostgreSQL 16 or newer.

Once, as the `postgres` superuser, create the role and the database:

```sql
CREATE ROLE catalog_app LOGIN PASSWORD 'change-me';
CREATE DATABASE course_catalog OWNER catalog_app;
```

Then, from the project folder:

```bash
python -m venv .venv
# On Windows: .venv\Scripts\Activate.ps1
# On Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
psql -h localhost -U catalog_app -d course_catalog -v ON_ERROR_STOP=1 -f seed.sql
fastapi dev main.py
```

REST docs: http://localhost:8000/docs. GraphiQL: http://localhost:8000/graphql.
The password `change-me` is for training; real projects don't commit passwords.

## What changed in the API

- **Ошибки REST в формате Problem Details (RFC 9457):** все ожидаемые бизнес-ошибки (`EMAIL_TAKEN`, `ALREADY_ENROLLED`, `COURSE_NOT_FOUND`, `STUDENT_NOT_FOUND`) и стандартные ошибки фреймворка возвращаются с заголовком `Content-Type: application/problem+json` и структурированным телом (поля `type`, `title`, `status`, `detail`, `instance`). Бизнес-правила и ограничения вынесены из маршрутов в изолированный слой `services.py` (`ServiceError`), а их трансляция в HTTP-ответы выполняется через обработчики исключений в `problem.py`.
- **Точка входа `/graphql` и GraphiQL:** подключен Strawberry GraphQL Router с маршрутом `/graphql`. При обращении через браузер открывается интерактивная среда GraphiQL со встроенной документацией схемы и автодополнением по `Ctrl+Space`. Сессия базы данных берется для каждого HTTP-запроса через фабрику контекста `Context(BaseContext)`, что исключает утечки сессий между запросами.
- **Мутации и контракт `userErrors`:** мутации `enroll` и `likeCourse` следуют соглашению GraphQL: принимают структурированный аргумент `input` и возвращают типизированный ответ-конверт (payload) со списком `userErrors`. Ожидаемые нарушения бизнес-правил возвращаются со статусом 200 OK внутри `data.<mutation>.userErrors`. Непредвиденные системные сбои возвращаются в верхнеуровневом ключе `errors`.
- **Счётчик SQL-запросов и заголовок `X-SQL-Queries`:** реализован измерительный middleware (`counter.py`), слушающий событие SQLAlchemy `before_cursor_execute` на движке `engine`. Количество обращений к базе данных подсчитывается в изолированном контексте `ContextVar` для каждого запроса и возвращается клиенту в заголовке `X-SQL-Queries`.
- **Многоуровневая защита GraphQL:**
  - `QueryDepthLimiter(max_depth=5)` блокирует запросы с чрезмерной вложенностью до их выполнения;
  - `MaxAliasesLimiter(max_alias_count=10)` ограничивает количество псевдонимов в одном запросе;
  - Функции `check_limit` и `parse_id` валидируют диапазоны аргументов в резолверах с понятными сообщениями `GraphQLError`;
  - `MaskErrors` маскирует внутренние непредвиденные исключения, предотвращая утечку структуры базы и SQL-запросов клиенту (возвращает `Unexpected error.`);
  - Интроспекция управляется переменной окружения `GRAPHQL_INTROSPECTION` (`config.py`).
- **Новые REST-маршруты:** добавлены эндпоинты `GET /students/{id}` и `GET /students/{id}/enrollments`, возвращающие данные студента и список его записей на курсы.

## Example queries

The “My courses” query (in the GraphiQL Variables panel: `{"id": "2"}`):

```graphql
query MyCourses($id: ID!) {
  student(id: $id) {
    name
    enrollments {
      id
      course {
        title
        credits
        level
      }
    }
  }
}
```

The `enroll` mutation and its answer on a repeated enrollment:

```graphql
mutation Enroll($input: EnrollInput!) {
  enroll(input: $input) {
    enrollment {
      id
      enrolledAt
      course {
        title
      }
    }
    userErrors {
      code
      message
    }
  }
}
```

Variables:
```json
{
  "input": {
    "courseId": "ai-integration",
    "studentId": "3"
  }
}
```

Response with `userErrors`:
```json
{
  "data": {
    "enroll": {
      "enrollment": null,
      "userErrors": [
        {
          "code": "ALREADY_ENROLLED",
          "message": "Student is already enrolled in this course"
        }
      ]
    }
  }
}
```

## REST vs GraphQL comparison

The “My courses” screen of student 2; numbers from `measure.py`, starting data.

| Criterion | REST | GraphQL | Source |
|-----------|------|---------|--------|
| Requests and rounds per screen | 5 requests, 2 rounds (round 1: student + enrollments; round 2: 3 courses) | 1 request, 1 round | `measure.py`, step 8 |
| Bytes in the responses | 1146 bytes | 339 bytes | `measure.py`, step 8 |
| SQL queries per screen | 5 SQL queries (1 student + 1 enrollments + 3 courses) | 3 SQL queries (DataLoader batching) | `measure.py`, `X-SQL-Queries` |
| SQL growth with more students | Linear growth (N+1): each student and enrollment triggers individual queries | Constant: 3 SQL queries per query tree regardless of row count | `try_n_plus_1.py`, experiments 4–5 |
| Error in the query text | HTTP 404 (route not found) / HTTP 422 (validation error) | HTTP 200, `data: null`, `errors` with location and `Did you mean...` hint | experiments 1 and 8 |
| Expected rule error (repeated enrollment) | HTTP 409, `application/problem+json`, `type: .../already-enrolled` | HTTP 200, `userErrors[0].code = ALREADY_ENROLLED` in payload | steps 1 and 4 |
| HTTP cache | Standard and native: caching per URL and GET method on browser/CDN level | Difficult: uniform POST to `/graphql`; requires client-side cache (Normalized Cache) | lecture section 14 |
| Protection from “expensive” queries | Route-level limits (built-in pagination, per-endpoint rate limiters) | Schema-level extensions: depth limiter, alias limiter, query complexity, argument checks | experiments 6 and 7 |

**Conclusion.** REST оптимален для простых CRUD-сценариев и публичных коллекций (например, каталог всех курсов `/courses`), где критически важна простота кэширования на уровне CDN и стандартные коды ответов HTTP. GraphQL демонстрирует подавляющее преимущество на сложных пользовательских экранах (таких как личный кабинет «Мои курсы»): он сокращает число запросов с 5 до 1, исключает задержку последовательных сетевых раундов (1 раунд вместо 2), передает в 3.4 раза меньше байт (339 против 1146), а использование DataLoaders предотвращает проблему N+1, сводя нагрузку на БД к фиксированным 3 запросам.

## Experiment log

| # | Experiment | What I saw | Cause | How I fixed it |
|---|------------|------------|-------|----------------|
| 1 | a typo in a field name (`titel`), an argument name in `snake_case` (`is_elective`) | HTTP 200, `data: null`, в `errors`: `Cannot query field 'titel' on type 'Course'. Did you mean 'title', 'level', or 'likes'?` и `Unknown argument 'is_elective'... Did you mean 'isElective'?` | Движок GraphQL валидирует синтаксис и типы запроса по схеме до выполнения резолверов. Имена аргументов в схеме Strawberry автоматически приводятся к camelCase. | Исправил имя поля на `title`, а аргумент на `isElective`. |
| 2 | `\| None` removed from the `course` query, a nonexistent course | HTTP 200, `data: null`, `errors`: `Cannot return null for non-nullable field Query.course.`. В запросе с псевдонимами `{ a: course(...) b: course("nope") }` результат поля `a` был уничтожен вместе с `b`. | Правило всплытия null (null propagation): возвращение null в поле, объявленном в схеме как обязательное (`!`), «поднимает» null к ближайшему nullable-родителю (в данном случае ко всему `data`). | Вернул аннотацию возвращаемого типа `CourseType \| None` в методе резолвера `course`. |
| 3 | a mutation with the GET method | HTTP 400 Bad Request (plain text): `mutations are not allowed when using GET`. Число лайков в базе не изменилось (осталось 12). | Спецификация GraphQL и семантика HTTP запрещают мутации через безопасный метод GET, чтобы исключить случайное изменение данных при переходе по ссылке или предзагрузке. | Мутации отправляются исключительно методом POST с телом JSON. |
| 4 | `more_students.sql`: 3 and 20 students, the SQL counter | До DataLoaders: 3 студента требовали 7 SQL-запросов, 20 студентов — 27 и 24 запроса. В GraphiQL задержка визуально не заметна, но нагрузка на БД выросла почти в 4 раза. | Проблема N+1: ленивая загрузка связанных сущностей ORM при обращении к атрибутам в цикле порождает отдельный SQL-запрос на каждый родительский объект (1 + N + M). | Подключил пакетную загрузку связей через DataLoaders (`batch_loader`), объединяющую выборки в `WHERE IN (...)`. |
| 5 | a DataLoader batch function that doesn't sort rows by key | Запрос студентов вернул `WrongNumberOfResultsReturned: expected: 3, received: 6`. Запрос записей с `order_by(column.desc())` вернул данные без ошибок, но у 4 из 6 записей курсы перепутались. | DataLoader сопоставляет результаты по позиционному индексу в возвращаемом списке. Нарушение порядка или длины списка приводит либо к исключению, либо к незаметной подмене чужих данных. | Сгруппировал строки через `defaultdict(list)` по значению внешнего ключа и вернул список строго в порядке переданных ключей `keys`. |
| 6 | six dangerous queries without protection and with it | Без защиты: цикл глубиной 6 и 12 псевдонимов выполнились (24 SQL-запроса на лайки); `limit -1` и 20-значный ID вывели клиенту SQL-текст, имена таблиц и параметров. С защитой: цикл и псевдонимы отклонены до выполнения (`exceeds maximum operation depth of 5`, `12 aliases found. Allowed: 10`); аргументы проверены (`limit must be between 1 and 100`, `Invalid ID: 'abc'`), а переполнение bigint замаскировано (`Unexpected error.`). | В GraphQL клиент сам формирует дерево запроса и может исчерпать ресурсы сервера. По умолчанию неотловленные исключения попадают в `errors` со всеми внутренними деталями. | Подключил расширения `QueryDepthLimiter`, `MaxAliasesLimiter`, валидаторы `check_limit` и `parse_id` в резолверах, а также расширение `MaskErrors`. |
| 7 | introspection off, a typo in a field name | Запрос `{ __schema { queryType { name } } }` отклонен: `GraphQL introspection has been disabled`. Однако запрос с опечаткой `{ cours { title } }` по-прежнему вернул подсказку `Did you mean 'course' or 'courses'?`. | Отключение интроспекции блокирует системные поля `__schema` и `__type`, но валидатор запросов продолжает генерировать подсказки по именам полей схемы. Скрытие схемы не заменяет авторизацию. | Восстановил `GRAPHQL_INTROSPECTION=true` для работы GraphiQL, зафиксировав понимание, что безопасность данных обеспечивается правами доступа пользователей, а не секретностью схемы. |
| 8 | client failures: a typo, no `errors` check, the API stopped | 1) Опечатка в поле: `GraphQLRequestError: Cannot query field 'titel'...`. 2) Без проверки `errors`: `TypeError: Cannot destructure property 'student'... as it is null`. 3) API остановлен: `TypeError: fetch failed`. | GraphQL возвращает HTTP 200 даже при ошибках в запросе. Без проверки ключа `errors` клиент падает на следствии (попытка прочитать свойства из `null`), скрывая первопричину с сервера. | В хелпере `gql` реализована обязательная проверка `if (body.errors?.length) throw new GraphQLRequestError(body.errors)`. |

## Decisions

- **Правила и их ошибки сосредоточены в `services.py`, а REST и GraphQL транслируют коды ошибок независимо.** Бизнес-правила приложения (уникальность email, проверка дубликата записи, существование курса и студента) не зависят от протокола передачи данных. Если валидировать правила отдельно в REST-маршрутах и GraphQL-мутациях, логика неизбежно рассинхронизируется при развитии проекта. Слой `services.py` принимает сессию SQLAlchemy и аргументы, выполняет операции и при нарушении выбрасывает `ServiceError(code, message)`. Слой REST (`problem.py`) сопоставляет код с HTTP-статусом и типом RFC 9457, а GraphQL-мутации оборачивают его в `userErrors`.
- **Экземпляры DataLoader создаются в `Context` на каждый запрос, а батч-функция сопоставляет строки по значению ключа.** DataLoader кэширует загруженные объекты по ключу в памяти. Если бы загрузчик был синглтоном на уровне приложения, данные одного пользователя (или результаты устаревших транзакций) отдавались бы другим пользователям в обход изоляции запросов. Батч-функция группирует строки через словарь `groups = defaultdict(list)` по значению ключа (`getattr(row, column.key)`), поскольку база данных не гарантирует совпадение порядка возвращаемых строк с порядком ключей в операторе `IN (...)`.
- **Двухуровневая защита: явная валидация `check_limit` / `parse_id` и `MaskErrors` для остального.** Расширение `MaskErrors` скрывает любые непредвиденные исключения, заменяя их на текст `Unexpected error.`. Однако для клиента, допустившего понятную ошибку (например, отрицательный лимит или строковый ID), такое сообщение неинформативно и мешает отладке. Поэтому понятные пограничные случаи проверяются в коде резолверов с выбросом `GraphQLError` с конкретным текстом («limit must be between 1 and 100», «Invalid ID: 'abc'»), а `MaskErrors` отлавливает только непредвиденные аварии (ошибки БД, сбои типов), скрывая от клиента внутренности системы и SQL-код.
