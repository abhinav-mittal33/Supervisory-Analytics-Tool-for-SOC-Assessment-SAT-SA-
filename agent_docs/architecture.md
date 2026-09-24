# Architecture
# Generated and maintained by Claude. Never edited manually.
# Updated whenever the system design changes.

## System Overview

[Claude fills — what the system does end to end in plain English]

## Component Diagram

```
[Claude fills — ASCII diagram of how components connect]

Example shape:
User → [Frontend] → [API Layer] → [Business Logic] → [DB]
                                ↓
                         [External Service]
```

## Request Flow

[Claude fills — step by step what happens from user action to response]

1.
2.
3.
4.

## Module Map

[Claude fills — what each directory/module is responsible for]

| Path | Responsibility | Must NOT |
|------|---------------|----------|
| `src/routes/` | HTTP routing only | Contain business logic |
| `src/services/` | Business logic | Access DB directly |
| `src/models/` | DB schema + queries | Contain business logic |
| `src/utils/` | Shared helpers | Import from services |

## Key Design Decisions

[Claude fills — every significant architectural choice and why]

## Boundaries

[Claude fills — rules about what can import what, what belongs where]

- [e.g. Routes call services. Services call models. Models do not call services.]
- [e.g. No business logic in route handlers.]

## What NOT to Change Without Discussion

[Claude fills as project matures — stable contracts and shared interfaces]

## Planned but Not Built

[Claude tracks scope explicitly — what's intentionally deferred]
