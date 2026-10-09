# PROGRESS

Read `CLAUDE.md` first. Tick a task as soon as it is done and its tests pass.

## Checkpoint 1 — skeleton, tooling, models, config
- [x] CLAUDE.md, PROGRESS.md
- [x] pyproject.toml (pinned deps, ruff, mypy, pytest, coverage config)
- [x] .gitignore, .gitattributes, .env.example, .dockerignore
- [x] Package skeleton (`src/ghostcite/`, `py.typed`, `__main__`, `cli.py` with `--version`)
- [x] models.py, config.py, errors.py, redact.py, logs.py, settings.py
- [x] tasks.py (install, fmt, lint, types, test, check, eval, web)
- [x] Test harness: `--allow-hosts` network block plus a canary test, verified on Windows with FastAPI TestClient (note: `--disable-socket` is deliberately not used; asyncio needs a loopback socketpair on Windows. Starlette 1.7 requires `httpx2` for TestClient)
- [x] Unit tests for models, config, errors, redaction, logs, settings, CLI version
- [x] .pre-commit-config.yaml (ruff, mypy, gitleaks); gitleaks verified on Windows (A6). Result: the golang hook builds and runs with Go 1.22, so detect-secrets is not needed. `.gitleaks.toml` adds a `serpapi-api-key` rule (the defaults have none). Detection was proven against a generated fake key (exit 1, output redacted), and `src/` scans clean. The hook only scans *staged* changes, so CI runs a separate full-history `gitleaks git` job with a checksum-verified release binary. Put this in CONTRIBUTING.md and ARCHITECTURE.md at Checkpoint 7.
- [x] CI workflow (3.11, 3.12: lint, types, tests, coverage; pre-commit hooks; gitleaks full history)
- [x] Gates green → STOP (ruff, format, mypy --strict, 49 tests, 99.7% coverage, all pre-commit hooks)

## Checkpoint 2 — ingest and parse
- [x] ingest/text.py, ingest/bibtex.py (malformed entry reporting, line numbers)
- [x] ingest/pdf.py (section detection, two-column, hyphenation, headers/footers, scanned PDF error)
- [x] parse/split.py, parse/fields.py, parse/names.py with per-field confidence; parse/cleanup.py; ingest/sections.py
- [x] document.py: content-based format detection, size/count limits, safe file names
- [x] PDFs generated in tests (tests/pdf_factory.py, reportlab); unit and Hypothesis property tests; edge cases
- [x] Gates green → STOP (237 tests, 99.37% coverage, all hooks)
  Note: the Write tool turns `\uXXXX` escapes into literal characters. After writing a file, scan it for
  non-ASCII characters and re-escape the code lines (ruff RUF001 flags ambiguous ones).

## Checkpoint 3 — search
- [ ] cache.py, budget.py, ratelimit.py, account.py (preflight)
- [ ] backends (live/cache/demo), client.py (retry, redaction, offline)
- [ ] parsers/scholar.py, parsers/google.py
- [ ] planner.py
- [ ] Mocked tests
- [ ] Live smoke test (≤ 5 searches), sanitized fixtures, credits.log
- [ ] Gates green → STOP

## Checkpoint 4 — match, verdict, reports, CLI
- [ ] match/normalize.py, match/score.py (fallback cap)
- [ ] verdict/rules.py, pipeline.py
- [ ] report: json, markdown, html, sarif (schema-validated)
- [ ] cli.py incl. --demo, exit codes
- [ ] Gates green → STOP

## Checkpoint 5 — web and Action
- [ ] FastAPI app, SSE progress, limits (A3), no-key demo banner (A2)
- [ ] Templates, JS, CSS (a11y, dark mode, responsive)
- [ ] action.yml plus an example workflow
- [ ] Tests
- [ ] Gates green → STOP

## Checkpoint 6 — evaluation
- [ ] eval/dataset.jsonl plus validate_dataset.py (Crossref/arXiv)
- [ ] eval/run.py; live eval in batches with credit logging
- [ ] Cache-only tuning; record fixtures; demo bundle
- [ ] Gates green → STOP

## Checkpoint 7 — docs and final verification
- [ ] README, docs/*, LICENSE, CONTRIBUTING, CoC, SECURITY, CHANGELOG, templates
- [ ] Dockerfile, compose.yaml
- [ ] samples/
- [ ] Fresh-venv quickstart check, all gates, secret/PII scan, hackathon checklist
- [ ] STOP

## Credits used
See `.dev/credits.log` (gitignored). Running total: 0 / 120.
