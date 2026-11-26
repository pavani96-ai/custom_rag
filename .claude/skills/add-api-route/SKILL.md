---
name: add-api-route
description: Add an HTTP endpoint following the project layout: route, Pydantic models, mocked test, and doc update.
model: haiku
effort: low
---

1. Add the handler to `src/app/api/routes.py`. Extend the existing router; do not replace earlier interfaces.
2. Put request and response models in `src/app/schema/models.py`.
3. Add a test in `src/tests/` that mocks all external services.
4. Update `docs/architecture.md` in the same change.
5. Run `make check`.
