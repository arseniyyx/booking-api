# booking-api

A small backend for booking shared stuff: meeting rooms, desks, a projector, whatever.
FastAPI + async SQLAlchemy + PostgreSQL.

I built it around one question: how do you make sure two people can't book the same room
for the same time, even if they click "book" at the exact same moment?

## The double-booking problem

The obvious way is to check for overlaps and then insert:

```python
if not await has_overlap(room, start, end):
    await insert_booking(...)
```

This breaks under load. Two requests run the check at the same time, both see a free slot,
both insert. You end up with two bookings for 10:00 in the same room.

Instead of locking in the app, I let Postgres enforce it with an exclusion constraint:

```sql
ALTER TABLE bookings ADD CONSTRAINT ex_bookings_no_overlap
EXCLUDE USING gist (resource_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&)
WHERE (status = 'confirmed');
```

In plain words: for the same `resource_id`, no two confirmed time ranges may overlap.

A few details that matter:

- `'[)'` makes the range half-open, so 10:00-11:00 and 11:00-12:00 don't conflict.
- The `WHERE` clause means a cancelled booking frees its slot right away.
- `btree_gist` is needed so one index can combine `=` on an integer with `&&` on a range.
- When the constraint fires, Postgres returns error `23P01`. The API turns that into `409 Conflict`.

There's a test that sends 10 booking requests for the same slot at once. Exactly one gets
`201`, the other nine get `409`.

## What else is in here

- Register / login with JWT, passwords hashed with bcrypt
- Two roles: users book things, admins manage resources and can see all bookings
- Resources: CRUD, pagination, can be deactivated instead of deleted
- Bookings: create, list with filters, cancel (calling cancel twice is fine)
- A "busy slots" endpoint so a frontend can draw a calendar without seeing who booked what
- If you ask for someone else's booking you get `404`, not `403`, so ids can't be probed
- Validation: must be in the future, 15 min to 8 h, timezone required
- Alembic migrations, and the tests run against the real migrated schema
- Docker Compose, GitHub Actions (lint, format, tests, docker build)

## Running it

```bash
docker compose up --build
```

API on http://localhost:8000, Swagger docs on http://localhost:8000/docs.

To make yourself an admin after registering:

```bash
docker compose exec api python -m app.cli promote you@example.com
```

Quick try with curl:

```bash
curl -X POST localhost:8000/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"supersecret"}'

TOKEN=$(curl -s -X POST localhost:8000/auth/login \
  -d 'username=you@example.com&password=supersecret' | jq -r .access_token)

curl -X POST localhost:8000/bookings -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"resource_id":1,"start_at":"2030-01-01T10:00:00Z","end_at":"2030-01-01T11:00:00Z"}'
```

## Endpoints

| Method | Path | Who | What |
|---|---|---|---|
| POST | `/auth/register` | anyone | create account |
| POST | `/auth/login` | anyone | get a token |
| GET | `/users/me` | user | who am I |
| GET | `/resources` | user | list active resources |
| POST | `/resources` | admin | add a resource |
| GET / PATCH / DELETE | `/resources/{id}` | user / admin / admin | read, edit, delete |
| GET | `/resources/{id}/busy?from=&to=` | user | taken time slots |
| POST | `/bookings` | user | book (`409` if taken) |
| GET | `/bookings` | user | my bookings (admins: `all_users=true`) |
| GET | `/bookings/{id}` | owner / admin | one booking |
| POST | `/bookings/{id}/cancel` | owner / admin | cancel |
| GET | `/health` | anyone | checks the DB too |

## Local development

You need Python 3.11+, [uv](https://docs.astral.sh/uv/) and Postgres 16.

```bash
uv sync
createdb booking_test
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/booking_test uv run pytest
uv run ruff check . && uv run ruff format --check .
```

The test setup runs the Alembic migrations once and truncates tables between tests. I
didn't want tests on `create_all()` because then the constraint above would only be tested
in theory.

## Layout

```
app/
  main.py        app + routers
  config.py      settings from env
  db.py          engine, session
  models.py      tables, including the exclusion constraint
  schemas.py     request / response models
  security.py    bcrypt + JWT
  deps.py        current user, admin check
  routers/       auth, resources, bookings
  cli.py         promote a user to admin
migrations/      alembic
tests/           pytest + httpx, real Postgres
```

## What I'd add next

- Refresh tokens and logout
- Recurring bookings ("every Monday 10:00")
- Opening hours per resource
- Rate limiting on login
