# Course Catalog API · Lab 9

FastAPI, PostgreSQL, SQLAlchemy, Strawberry GraphQL. Продолжение лабораторных 4–8: добавлены Argon2id, JWT, роли и проверка владельца.

Frontend: [course-catalog-lab5](https://github.com/Daniil37474/course-catalog-lab5).
Предыдущий отчёт сохранён в [docs/LAB8.md](docs/LAB8.md).

## Запуск на Windows

Требуются Python 3.11+ и PostgreSQL. Для отдельной учебной БД можно использовать Docker Desktop:

```powershell
git clone https://github.com/Daniil37474/course-catalog-api-lab5.git course-catalog-api
cd course-catalog-api
docker compose up -d --wait database
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
Copy-Item .env.example .env
$key = .venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
(Get-Content .env -Raw).Replace("SECRET_KEY=", "SECRET_KEY=$key") | Set-Content -Encoding ascii .env
.venv\Scripts\python.exe bootstrap.py --reset-demo
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Docker публикует PostgreSQL только на localhost:5433. Для своей PostgreSQL создайте отдельную БД course_catalog_lab9 и измените DATABASE_URL в .env.
SECRET_KEY обязателен и должен содержать не менее 32 символов. Настоящие .env и ключи не хранятся в Git.
bootstrap --reset-demo заменяет учебные данные и запрещён за пределами БД/схем Lab 9.
Для обновления без сброса: `alembic upgrade head`, затем `python seed_users.py`.

Swagger: http://127.0.0.1:8000/docs. GraphQL: http://127.0.0.1:8000/graphql.

## Демонстрационные аккаунты

| Роль | Email | Пароль | studentId |
|---|---|---|---|
| student | aigerim@example.com | aigerim-demo-pass | 1 |
| student | daniyar@example.com | daniyar-demo-pass | 2 |
| admin | admin@example.com | admin-demo-password | нет |

Пароли открыты исключительно для локальной учебной демонстрации. В таблице users хранятся Argon2id-хеши.
Повторный seed_users не меняет пароли существующих аккаунтов.

## Реализация

- Миграция 0003 добавляет users и сохраняет существующие данные.
- security.py: Argon2id, DUMMY_HASH, HS256, exp/sub/iss/iat и проверка идентификатора bigint.
- auth.py: /auth/login, get_optional_user, get_current_user, require_admin, can_access_student.
- /me не возвращает password_hash. Роль загружается из БД при каждом запросе.
- GET /enrollments доступен admin; POST /enrollments проверяет владельца.
- REST-профиль и записи студента доступны ему самому и admin; POST /students доступен admin.
- GraphQL me, students и Student.email защищены permission classes. Мутация enroll также проверяет владельца.

## Реальная матрица REST

Проверено запросами к работающему серверу; `verification/api-results.json`.
Student здесь — Aigerim (studentId=1). Для POST выбраны ещё не занятые пары courseId/studentId.

| Запрос | Anonymous | Student | Admin |
|---|---:|---:|---:|
| GET /courses | 200 | 200 | 200 |
| GET /me | 401 | 200 | 200 |
| GET /enrollments | 401 | 403 | 200 |
| POST /enrollments за себя (studentId=1) | 401 | 201 | нет собственного профиля |
| POST /enrollments за другого (studentId=2) | 401 | 403 | 201 |

401 сопровождается `WWW-Authenticate: Bearer`. Отказы REST используют `application/problem+json`.
Повторная разрешённая запись в уже выбранный курс возвращает 409 — это бизнес-ошибка, а не отказ авторизации.
На защищённых маршрутах проверка пользователя выполняется до изменения данных.
На публичном /courses отсутствие токена допустимо; предъявленный неверный токен даёт 401.

## Таблица угроз · Practical session 9

| Где | Что может сломаться | Что сделано и как проверено | Что остаётся |
|---|---|---|---|
| Форма входа | Перебор; разные ответы или время для известного и неизвестного email | Одинаковые 401 и Problem Details; DUMMY_HASH запускает Argon2id даже при неизвестном email. По 12 чередующихся запросов: медианы 207.25 мс для неизвестного email и 217.40 мс для неверного пароля известного пользователя. Это наблюдение на данной машине, не доказательство строгого постоянства времени. | Rate limiting не реализован, как в образце лекции. Добавить общий лимитер на /auth/login по нормализованному аккаунту и IP, например Redis; при превышении 429 и Retry-After. |
| Пароли и ключ | Утечка plaintext; ключ в репозитории или слишком короткий | В users только $argon2id$; разные соли дают разные хеши. Тесты проверяют отказ старта без ключа и с коротким ключом. .env исключён из Git; .env.example содержит пустой SECRET_KEY. | Для реального сервиса дополнить журналом входов и восстановлением пароля. |
| Токен и роль | alg:none, чужая подпись, истечение, нет exp, подмена роли | Сервер задаёт algorithms=[HS256], require=[exp,sub,iss,iat], проверяет issuer и bigint sub. Все семь вариантов live-проверки дают 401; дополнительные варианты есть в pytest. Роль читается из БД: изменение роли действует с тем же токеном. | Ключ меняется при компрометации; для плавной ротации потребовались бы kid и набор ключей. |
| Права на объекты | Чужой studentId (BOLA); забытый маршрут; обход защиты email другим путём | Реальная матрица выше; REST-профили проверяют владельца; GraphQL enroll проверяет владельца; Student.email защищён на типе. Проверены student, enrollments→student и course→enrollments→student: чужой email null, имя сохраняется, errors указывает путь. | Новые маршруты проверяются той же матрицей; имена и GraphQL-связи записей открыты согласно политике лекции. |
| Cookie и Next.js | Чтение токена из JS, HTTP, защита только в proxy, прямой вызов action | HttpOnly, Secure, SameSite=Lax, Path=/, Max-Age из expires_in. verifySession обращается к API на странице и в действии записи. Браузерные сценарии проверяют document.cookie, подделку cookie и прямой POST action без сессии. | Для размещения вне localhost требуется HTTPS. Next.js проверяет Origin/Host Server Actions; SameSite помогает против CSRF. |
| Выход и срок жизни | Скопированный JWT работает после выхода | Sign out удаляет cookie; повторный /account отправляет на /login. Браузерный тест сохраняет bearer, выходит и подтверждает /me=200 с копией. JWT живёт до exp, 15 минут. | Добавить token_version в users и JWT и увеличивать его при полном выходе; либо blacklist jti до exp. Refresh tokens при добавлении хранить с отзывом и ротацией. |

Cookie Secure включён и локально: открывайте frontend именно через `http://localhost:3000`.
Chromium/Edge допускают Secure-cookie на localhost; для обычного домена нужен HTTPS.
JWT содержит идентификатор и технические claims; пароль и роль в него не записываются.
Next.js не имеет SECRET_KEY: подпись проверяет API.


## Swagger и curl

В Swagger нажмите Authorize, в username введите email, затем вызовите /me.
Вход через Swagger и curl проверен на работающем сервере.

```powershell
$login = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/auth/login -Body @{
    username = "aigerim@example.com"
    password = "aigerim-demo-pass"
}
$token = $login.access_token
curl.exe -i http://127.0.0.1:8000/me -H "Authorization: Bearer $token"
curl.exe -i http://127.0.0.1:8000/enrollments -H "Authorization: Bearer $token"
curl.exe -i http://127.0.0.1:8000/me
```

Ожидается соответственно 200, 403 и 401.

## GraphQL

POST `http://127.0.0.1:8000/graphql`; для авторизации заголовок `Authorization: Bearer <token>`.

```graphql
{ me { id email role studentId } }
{ students { id name email } }
{ student(id: "2") { name email } }
{ enrollments(limit: 4) { student { id name email } } }
mutation {
  enroll(input: { courseId: "api-design", studentId: "1" }) {
    enrollment { id }
    userErrors { code message }
  }
}
```

Без токена me и students дают HTTP 200 с errors. Чужой email возвращается как null с errors, остальные разрешённые поля сохраняются.
Неверный bearer отклоняется до исполнения GraphQL обычным HTTP 401.
Проверяются и HTTP-статус, и массив errors.


## Проверки

65 backend-тестов прошли. Также прошли alembic check, 5 frontend unit-тестов и 7 браузерных сценариев, включая Swagger Authorize, поддельную cookie и прямой вызов Server Action без сессии.
Результаты: [verification/checks.json](verification/checks.json), [живые HTTP-запросы](verification/api-results.json), [браузер](verification/browser-results.json).
Браузерные тесты находятся в frontend-репозитории.

Создайте выделенную тестовую БД и запустите:

```powershell
docker compose exec -T database psql -U catalog_app -d course_catalog_lab9 -c "CREATE DATABASE course_catalog_lab9_test;"
$env:TEST_DATABASE_URL = "postgresql+psycopg://catalog_app:catalog_demo_password@localhost:5433/course_catalog_lab9_test"
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m alembic check
```

Тесты запрещают обычную БД. Разрешена БД с окончанием _test либо отдельная схема lab9_test с параметром URL `?options=-csearch_path%3Dlab9_test`.
Каждый тест откатывает свои изменения. Во время выполнения этой работы использовались изолированные схемы lab9_demo и lab9_test, исходные public-таблицы не менялись.

Для live-матрицы сначала выполните bootstrap --reset-demo, запустите API, затем в другом окне `python verify_lab9.py`.
Проверка добавляет две учебные записи, поэтому перед повторным измерением нужен новый reset-demo.

## Коротко для защиты

- Аутентификация определяет пользователя, авторизация проверяет его права.
- 401 — нет действительных credentials; 403 — пользователь известен, действие запрещено.
- Argon2id замедляет перебор хешей; соль хранится внутри строки хеша.
- JWT подписан, но не зашифрован; payload читается без ключа.
- studentId из запроса не доказывает владение. API сравнивает его с user.student_id.
- GraphQL-поле защищают на типе, потому что до него можно дойти разными путями.
- proxy.ts проверяет наличие cookie; DAL и API проверяют подлинность и права.
- Удаление cookie не отзывает уже скопированный JWT.

## Документация

- [FastAPI: OAuth2, hashing, JWT](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
- [Next.js: Authentication](https://nextjs.org/docs/app/guides/authentication)
- [Strawberry: Permissions](https://strawberry.rocks/docs/guides/permissions)
