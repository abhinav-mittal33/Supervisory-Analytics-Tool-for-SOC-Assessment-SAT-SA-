# Gotchas
# Maintained by Claude. Read first when something unexpected happens.
# Add an entry every time a non-obvious problem is found or decision is made.

## Entry Format
**[Short title]**
- Symptom: [what you observe]
- Cause: [why it happens]
- Fix: [exact solution]
- File: `[affected file or module]`

---

## Environment & Config

**Missing env var fails silently with None**
- Symptom: Feature returns wrong data or breaks with no clear error
- Cause: `os.getenv("VAR")` returns None if var is missing, no exception raised
- Fix: Use `os.environ["VAR"]` (raises KeyError) or validate all required vars at startup and refuse to boot if any are missing
- File: Any file reading env vars

**ORM N+1 query on list endpoints**
- Symptom: List endpoint is slow; DB query count scales with the number of rows returned
- Cause: ORM lazy-loads related objects inside a loop — one query per row
- Fix: Eager-load with a JOIN or `select_related` / `include` / `.options(joinedload(...))` at the query level
- File: Any model/service that returns a list of objects with nested relations

**JWT expiry not validated**
- Symptom: Expired tokens continue to work after their stated expiry
- Cause: Token signature is validated but the `exp` claim is never checked
- Fix: Always decode with `options={"verify_exp": True}` (or equivalent); ensure middleware rejects 401 on expiry
- File: Auth middleware / token decode utility

**Tests pass alone but fail in parallel**
- Symptom: Full test suite has intermittent failures; individual tests pass in isolation
- Cause: Tests share DB state — inserts/updates from one test bleed into another
- Fix: Wrap each test in a transaction that rolls back after the test, or use a separate test DB seeded fresh per run
- File: Test fixtures / conftest.py / jest setup

---

## [Claude adds entries here as the project is built]

## Database

## API

## Auth

## Frontend

## External Services

## Deployment
