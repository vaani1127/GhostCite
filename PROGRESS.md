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
- [x] cache.py, budget.py (incl. CombinedBudget for web), ratelimit.py (token bucket), account.py (preflight)
- [x] backends.py (LiveTransport, DemoBundle), client.py (retry, redaction, offline), sanitize.py
- [x] parsers/scholar.py, parsers/google.py (incl. Knowledge Graph candidate)
- [x] planner.py (exact title, then title + author:, then Google fallback for books/theses with gl=in)
- [x] Mocked tests
- [x] Live smoke test: 5 fixtures in tests/fixtures/serpapi, credits.log updated. **7 credits used in total** (6 for the first run, because a timed-out request was still billed; 1 to re-record the Google fixture with gl=in)
- [x] Gates green → STOP (350 tests, 99.60% coverage)
  Findings from real data (all fixed and tested): `markdown_endpoint` and thumbnail links under serpapi.com/searches/ are
  now sanitized; Scholar venues can start with "…"; Google needs `gl` for stable results; timeouts can be
  billed, so `credits_used` counts them and retries re-reserve budget.
  For Checkpoint 6: the demo-bundle builder must run `sanitize_response` on export (older local cache entries predate
  the stricter sanitizer).

## Checkpoint 4 — match, verdict, reports, CLI
- [x] User changes before Checkpoint 4: 75 s timeout; at least 15 s before a retry after a timeout; identical params; a retry
  served from SerpApi's cache (original `search_metadata.created_at` older than the send time minus a 10 s margin;
  verified with a free probe, since SerpApi has no explicit cache flag) is refunded; hl=en is pinned by a test; cap 150, keep >= 80 unused.
- [x] match/normalize.py, match/score.py (fallback cap, subtitle tolerance, abbreviations, transliteration)
- [x] verdict/rules.py (6 ordered rules, template reasons, integrity score), pipeline.py (dedupe, parallel, stop at title match)
- [x] service.py (live/offline/demo, preflight, shared budget), samples.py
- [x] report: json, markdown, html (self-contained, CSP, escaped), sarif (validated against the vendored OASIS schema)
- [x] cli.py: check (table/json/md/html/sarif, --output infers the format, stdin, --demo, --offline, --fail-on), cache stats/clear
- [x] Gates green → STOP (501 tests, 99.49% coverage)
  Splitter fix: small numbering gaps ([1],[2],[4]) are accepted, so references are no longer merged silently.
  For Checkpoint 7: add hatch force-include `samples` → `ghostcite/_samples` once samples/ exists (a missing folder breaks the build).
  For Checkpoint 6: a misquoted title ("Attention is all we need for sequence transduction") scores below title_reject.
  Review the title-similarity choice with eval data.

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
See `.dev/credits.log` (gitignored). Running total: 7 / 150 (account: 243 left). Keep >= 80 unused on the account after the eval.
