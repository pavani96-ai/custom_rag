# Security

- Never hardcode secrets, API keys, tokens, or passwords. Use environment variables.
- Never commit `.env` or key files. Only commit `.env.example` with placeholder names.
- Never log secrets or full auth headers.
- Validate and sanitize all external input at API boundaries (Pydantic models).
- Use parameterized queries for every database and search call. Never build queries by string concatenation.
- Use Workload Identity Federation in CI. No static cloud keys.
- Ask before any destructive or production-changing command.
- Never commit directly to `main`. Use a feature branch and a pull request.