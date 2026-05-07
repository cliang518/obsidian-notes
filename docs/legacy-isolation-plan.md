# Legacy Isolation Plan

## Intent

Keep the legacy system available for reference and current production usage while preventing it from contaminating the V2 rebuild line.

## Rules

- new architecture work lands only under `platform_v2/`
- legacy runtime data stays under legacy directories
- V2 gets its own database file and startup scripts
- V2 does not import legacy SQLAlchemy models
- V2 can reuse legacy environment tools only when explicitly isolated

## Practical outcome

- current users can keep using the legacy system
- V2 can evolve in parallel
- later deployment to a dedicated server becomes straightforward

