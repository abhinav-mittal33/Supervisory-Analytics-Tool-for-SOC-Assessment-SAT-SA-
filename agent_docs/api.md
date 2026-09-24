# API Reference
# Generated and maintained by Claude as endpoints are built.

## Base URLs

- Dev: `http://localhost:[port]`
- Prod: `[Claude fills when deployment is set up]`

## Auth

[Claude fills — how requests are authenticated]
Header format: `[e.g. Authorization: Bearer <token>]`
Token obtained via: `[endpoint]`

## Standard Response Format

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

On error: `{ "success": false, "data": null, "error": { "code": "", "message": "" } }`

## Endpoints

[Claude adds each endpoint as it's built]

| Method | Path | Purpose | Auth | Request body | Response |
|--------|------|---------|------|-------------|----------|
| POST | `/auth/login` | Authenticate user | No | `{email, password}` | `{token}` |
| GET | `/health` | Health check | No | — | `{status: ok}` |

## Error Codes

| HTTP | Meaning |
|------|---------|
| 400 | Validation failure — bad input |
| 401 | Not authenticated |
| 403 | Authenticated but not authorized |
| 404 | Resource not found |
| 500 | Server error — logged server-side, generic message to client |

## Rules

- Input validated before any business logic runs.
- 500 errors: full stack trace logged server-side only. Client gets a generic message.
- Never expose internal IDs if public UUIDs exist.
- New endpoints documented here before the PR is merged.
