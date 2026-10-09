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
- [x] User changes before Checkpoint 5: (1) Middle band: a reworded title (overlap >= title_reject) whose first author and year (+-1) agree
  gives METADATA_MISMATCH "Title differs from the closest real paper: '<title>' (<year>)."; otherwise NOT_FOUND
  with the closest candidate shown. A title match now also requires the same significant words, so "Attention is all
  *we* need" (similarity 0.898) can never be VERIFIED. (2) Versions: the candidate agreeing on the most fields
  wins; a versions note is added for year/venue-only mismatches when versions.total > 1. Real fixture:
  Faster R-CNN (NeurIPS 2015 and TPAMI 2016), 1 credit.
- [x] Bugs found while testing: a single pasted "[1] ..." reference kept its marker (it broke the first author);
  identical concurrent queries double-spent (now single-flight per cache key).
- [x] FastAPI app (web/app.py, web/jobs.py), SSE progress, limits (A3), no-key demo banner (A2), security headers,
  uploads read in memory with a streaming size cap (nothing written to disk), content-based type checks
- [x] Templates, JS, CSS (labels, aria-live, keyboard, focus styles, dark mode with a toggle, responsive)
- [x] Report page: download buttons for all formats, sorting, back link (the CLI HTML export stays standalone)
- [x] `ghostcite web` (127.0.0.1 by default, warning for non-loopback); verified as a real process
- [x] action.yml (composite; inputs via env only; cache restore; SARIF upload; job summary rendered offline)
  plus docs/examples/ghostcite-workflow.yml; the action script is tested under real bash with a fake CLI
- [x] Gates green → STOP (586 tests, 99.35% coverage)

## Checkpoint 6 — evaluation
- [x] Guard tests for harmless title differences (tests/unit/test_title_variants.py): dropped subtitle, "…" truncation,
  hyphenation and spacing, British/American spelling, "2"/"two", LaTeX and curly quotes. All VERIFY; no threshold lowered.
- [x] eval/dataset.jsonl: 67 rows (47 real incl. 19 Indian, 20 fabricated in 5 perturbation types). validate_dataset.py
  checked all against Crossref/arXiv: 67 passed, 0 dropped.
- [x] Family-level stratified split, seed 20261009: 28 tuning / 39 test. Four reference styles plus a BibTeX run.
- [x] eval/run.py: replay (default, eval/responses.json), --cache, --live (preflight, --reserve 80), --record.
- [x] Held-out first run preserved (eval/results_heldout_first_run.*): false alarms 6/28 (21.4%), detection 8/11 (72.7%).
  Six of nine failures came from Scholar's new bullet summary layout; fixed with fixtures and tests. Post-fix rerun
  (not held-out): 1/28 and 11/11. docs/EVALUATION.md lists every failure with its cause.
- [x] samples/ (sample.bib, sample.txt) and demo bundle (15 trimmed, sanitized responses); wheel ships samples.
- [x] Repo URL: vaani1127/GhostCite everywhere.
- [x] Web UI polish: hero line, how-it-works strip, inline hints on disabled controls, one-click demo (Demo mode with
  no input runs the sample), report summary card (score, verdict chips, mode, credits), shared 1080px width, theme
  sync between pages. Checked at 1366x768 and 1920x1080 in both themes with headless Edge.
- [x] Gates green → STOP

## Checkpoint 7 Part A — frozen held-out evaluation v2
- [x] eval/dataset_v2.jsonl: 26 rows (16 real: 9 international in new fields, 7 Indian; 10 fabricated, 2 per type),
  no paper shared with v1 (enforced by tests/unit/test_eval_datasets.py), all 26 validated against Crossref
- [x] Frozen before any search: sha256:e7e75254...8604 in docs/EVALUATION.md and eval/run.py (run refuses on change)
- [x] Run once (estimate 39, cap 40): 29 searches. False alarms 1/16 = 6.2% [1.1, 28.3], detection 8/10 = 80.0%
  [49.0, 94.3]; Indian 0/7 and 4/5. Failures: Granovetter 1977 reprint; two fake venues missed (one-word real venue
  not judged). Not fixed (freeze). Replay: eval/responses_v2.json (29 responses), verified identical.
- [x] Every live path (CLI, web, eval) appends to the credits log via ghostcite.credits; tests for both
- [x] Hygiene scan covers eval/, samples/, tests/fixtures/ (keys, e-mails, archive links, endpoint keys, CRLF)
- [x] LF line endings: writers use newline="\n"; 20 CRLF data files converted
- [x] Wilson intervals on every rate; counts only below n=5
- [x] Gates green → STOP

## Checkpoint 7 — docs and final verification
- [ ] README, docs/*, LICENSE, CONTRIBUTING, CoC, SECURITY, CHANGELOG, templates
- [ ] Dockerfile, compose.yaml
- [ ] samples/
- [ ] Fresh-venv quickstart check, all gates, secret/PII scan, hackathon checklist
- [ ] STOP

## Credits used
See `.dev/credits.log` (gitignored). Running total (logged runs): 121 / 150 (account: 126 left after v2; an unexplained 3-search drop between 04:43 and 08:33 UTC is noted in the log, and every live path now logs). Keep >= 80 unused on the account after the eval.
