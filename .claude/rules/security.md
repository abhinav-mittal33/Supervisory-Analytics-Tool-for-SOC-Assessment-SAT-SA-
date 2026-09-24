# Security Rules
# No paths: frontmatter — loads every session, applies everywhere.
# These are the rules too important to be context-dependent.

## Secrets — Non-Negotiable
- Secrets go in .env only. Never in source files, config files, or comments.
- .env must be in .gitignore. Verified at every session start.
- New env vars: add the name (not the value) to .env.example.
- If you write a value that looks like a secret into any source file — stop immediately.

## Input Validation — Applied at Every Entry Point
- Validate before any business logic runs
- Reject and return an error on invalid input — never silently discard or coerce
- User input never reaches: SQL queries, shell commands, template rendering, eval()
- File paths from user input: validate against an allowlist of allowed directories

## Authentication
- Use established libraries — never custom crypto or custom auth flows
- Passwords: bcrypt or argon2 with appropriate cost factor — never MD5/SHA1/SHA256
- Sessions: server-side expiry enforced, invalidatable on logout
- Tokens: short-lived access tokens + rotatable refresh tokens
- Auth checks: middleware applied at the router level, not inside individual handlers

## HTTP Security
- Set these headers on every HTTP response:
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
  - `Content-Security-Policy` — define explicitly, avoid `unsafe-inline` without nonce/hash
  - `X-Frame-Options: DENY` (or SAMEORIGIN if embedding your own content)
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
- CORS: explicit origin allowlist only. Never `Access-Control-Allow-Origin: *` on routes that accept credentials or auth tokens.
- Rate limiting on all auth endpoints: login, register, forgot-password, token refresh.
- Rate limiting on all public write endpoints (POST, PUT, PATCH, DELETE).

## Output Safety
- Never send stack traces to client in any environment except local dev
- Never log: passwords, tokens, session IDs, credit card numbers, SSNs, PII
- API errors: log full detail server-side, return generic message to client
- File downloads: Content-Disposition header set to prevent execution

## Dependencies
- Before adding any new package: check npmjs.com/pypi.org for publisher legitimacy
- Run pip-audit or npm audit when adding dependencies
- Lock files committed and reviewed on updates
- No packages with critical/high CVEs without documented mitigation

## Git & Repository Hygiene — Non-Negotiable
- .gitignore must exist before any first commit. Verify it contains at minimum:
  `node_modules/`, `.next/`, `dist/`, `build/`, `.env`, `.DS_Store`, `*.psd`, `*.log`, `coverage/`
- Never commit: node_modules, .next, dist, build, .DS_Store, *.psd, *.log, coverage dirs — bloat + exposure
- Infrastructure configs (docker-compose.yml, nginx.conf) that reveal internal ports/services/architecture:
  gitignore or keep in a private repo. Never push to a public repo without stripping sensitive values.
- Prisma schema, seed files, and DB migration files reveal table structure and business logic — restrict to private repos or ensure no sensitive defaults are seeded
- Test utilities, scripts, and internal tools: gitignore or keep in private dirs; never mix with public root
- Every repo needs secret scanning (GitHub secret scanning or equivalent), Dependabot/Renovate for CVE alerts, and a lint/audit step in CI before merge
- "Push first, fix later" = unacceptable. Security checks run before merge, not after.

## Cookie Security
- Every auth cookie must have ALL three flags: `HttpOnly`, `Secure`, `SameSite=Strict` (or `Lax`)
- `HttpOnly` alone is insufficient: missing `Secure` = cookie sent over plain HTTP; missing `SameSite` = CSRF vulnerability
- Verify cookie flags in every auth handler before shipping

## Auth Response Safety
- Never return the full user object from auth endpoints (login, register, token refresh)
- Explicitly whitelist response fields: `{ id, email, role }` — strip password_hash, internal flags, admin metadata, created_at, raw DB columns
- Return the minimum identity data the client actually needs, nothing more

## Error Handling — Auth and DB Calls
- Every auth and DB call must be wrapped in try/catch (or async equivalent)
- On failure: log full error server-side (with stack, query context); return only a generic message to client: "Authentication failed" or "Something went wrong"
- Stack traces, DB errors, query strings, and table names must never appear in HTTP responses

## Default Credentials — Never
- Never publish test/demo/default credentials anywhere in the repo: README, docs, seed files, comments
- For documentation examples use obvious placeholders: `username` / `CHANGEME-BEFORE-DEPLOY`
- CI must fail if string `admin/admin`, `admin/password`, or `root/root` appears in committed files outside of test directories

## Stack Exposure Prevention
- Remove `X-Powered-By` and `Server` response headers before production deployment
- Never include exact dependency versions, internal routes, or service names in public-facing error messages
- Avoid exposing framework fingerprints (e.g. Next.js `__NEXT_DATA__` with sensitive values) in rendered HTML

## The One Rule That Covers Everything
If user-controlled data touches a sensitive operation (query, command, file, render),
there must be explicit validation between the input and the operation.
No exceptions. No "we'll add it later."
