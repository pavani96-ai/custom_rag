---
name: production-code
description: Write production-ready code for this repo: small named functions, each placed in its layout folder, with type hints, docstrings, validation, parameterized queries, and tests. Use before writing or changing any Python or TypeScript code here.
---

Follow `.claude/rules/code style.md`, `security.md`, and `testing.md`. Then apply these steps.

1. **Find the home first.** Put each piece in the folder that owns it, per the layout in `CLAUDE.md`:
   - HTTP handlers: `src/app/api/routes.py` only.
   - Pydantic request, response, and provider models: `src/app/schema/models.py` only.
   - Settings: `src/app/config/settings.py`. Read config only through it.
   - Ingest and chunking: `src/app/rag/`. Provider clients: `src/app/rag/providers/`.
   - Database access: `src/app/db/`. SQL is parameterized and read-only where possible.
   - Search index code: `src/app/search/`. Storage: `src/app/storage/`. Logging: `src/app/observability/`.
   - Web UI: `apps/web/app/` for pages, `apps/web/lib/` for shared logic.
   If no folder fits, say so and propose one before creating it.

2. **Keep each function small.** One function does one step. Target 20 lines or fewer, with no nesting deeper than two levels. Pull each branch or loop body into a named helper. Prefer early returns over nested `if`/`else`. Prefer plain code over clever code.

3. **Write types and docs on every function.** Python: type hints on all parameters and return values, and a one-line docstring. TypeScript: a JSDoc comment on each exported function. Names are `snake_case` in Python.

4. **Validate at the boundary.** Every external input (HTTP body, upload, provider response) goes through a Pydantic model. Check the file type and size before storing. Never build SQL or search queries by string concatenation.

5. **Keep secrets and identifiers out of code.** No keys, passwords, project IDs, or regions in source. Never log secrets or full auth headers. Keep operational IDs and upload times out of model and embedding text.

6. **Handle failures explicitly.** Catch specific exceptions. Return a clear error to the caller, and log it with a request or job ID. Do not swallow errors silently.

7. **Add tests in `src/tests/` or `apps/web/tests/`.** Every new feature or bug fix needs a test. Mock all external services, and count provider calls where caching is involved.

8. **Check line length.** Keep lines at 100 characters or fewer.

9. **Verify before saying done.** Run `make check` in Docker and report its result. Update `docs/architecture.md` when a contract, route, or cache identity changes. Add a dated CHANGELOG entry at the end of the session.
