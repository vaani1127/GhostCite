# CLAUDE.md — working rules for GhostCite

Read this file and `PROGRESS.md` first after any context compaction or session restart, then continue from the first unchecked task in `PROGRESS.md`. The approved plan is mirrored in `PROGRESS.md`.

## What GhostCite is
A deterministic checker for hallucinated or wrong academic citations. Input: PDF, `.bib`, or pasted text. Each reference is searched on Google Scholar through SerpApi and gets a verdict (`VERIFIED | METADATA_MISMATCH | NOT_FOUND | UNPARSEABLE | SKIPPED_BUDGET`), a confidence in [0, 1], the parsed fields, the best candidate, the mismatched fields, and a one-line reason. The document summary has counts, an integrity score (documented formula) and the credits used. **No LLM anywhere in the pipeline.**

Context: SerpApi India Hackathon 2026, track "Knowledge & Public Interest", deadline 2026-10-10 23:59 IST. Judges read the code, tests, docs and git history. SerpApi must be core. Leaked keys or personal data disqualify. AI use must be disclosed (built with Claude Code).

## Hard boundaries
- Work **only** inside `F:\Hackathons\Microsoft\GhostCite`. Never read, list or search outside it (no globbing from the workspace root).
- Use `.\.venv\Scripts\python.exe` (3.12 locally; 3.11+ supported). Install only into this venv. The shell is PowerShell; CI runs on ubuntu-latest, so everything must work on both.
- **No git write commands** (add, commit, push, reset, checkout, rebase, stash…). Read-only `git status` / `git diff` are fine. The branch is `main`. Suggested commit messages never carry a `Co-Authored-By` or any other AI attribution trailer; AI use is disclosed in the README instead.
- **Never read or print `.env`.** The API key comes only from the environment or `.env`, is never logged or echoed, and is redacted from every log line and exception.
- **Never run commands that print environment values**, such as `docker compose config` without `--quiet`, `env`, `printenv`, `set`, or `Get-ChildItem Env:`. They expand `.env` and print the real key. (A `docker compose config` run on 2026-10-10 exposed the key, which then had to be rotated.)

## Quality bar
- src layout `src/ghostcite/`, one concern per module, fully typed, small pure functions, docstrings on all public API, comments explain *why*.
- No dead code, TODOs, stubs, placeholder logic, fake output, or silent `except`.
- Every threshold and weight lives in `config.py`, each with a comment explaining why.
- Gates (all must pass before any checkpoint): `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` with ≥ 90 % coverage. Run them with `.\.venv\Scripts\python.exe tasks.py check`.
- Dependencies are pinned and permissive only (MIT/BSD/Apache/ISC). No PyMuPDF or any GPL/AGPL package. Hypothesis (MPL-2.0) is approved as test-only.

## Tests
- No test touches the network or spends credits: pytest-socket blocks every host except localhost, and a canary test proves it.
- Fixtures are sanitized recorded SerpApi JSON. A hygiene test fails on anything key-like.
- The SARIF schema is vendored, never fetched.

## SerpApi facts (verified from the docs, 2026-10-08)
- `serpapi==1.1.2`: `Client(api_key, timeout)`, `.search(dict)` returns `SerpResults` (UserDict, `.as_dict()`). Non-2xx raises `serpapi.HTTPError` (`status_code`, `error`). Also `HTTPConnectionError` and `TimeoutError`, all under `SerpApiError`. A 200 body containing `error` does NOT raise. The client adds `api_key` to the params dict it receives, so always pass a copy.
- SerpApi's own cache is 1 h, exact params only, and free. Errored searches are free. An empty successful search costs 1. The Account API is free; extract only the count fields (its response contains the key and an email).
- Status codes: 400 bad param, 401 bad key, 403 account, 429 hourly limit or out of searches, 5xx server. The 200 message "Google hasn't returned any results for this query." means no candidates.
- Scholar result fields: `title, link, result_id, type, snippet, publication_info.summary, publication_info.authors[name, author_id], inline_links.cited_by.total, inline_links.versions.cluster_id`.

## Credits (hard cap: 150 live searches for the whole project; raised from 120 by the user on 2026-10-09)
- Before each live run: estimate the cost, check the Account API (counts only), and append `date | purpose | estimated | actual` to `.dev/credits.log` (gitignored). If a run would exceed the cap, stop and ask the user.
- At least 80 searches must remain unused on the SerpApi account after the eval (for the demo recording and final checks). If the eval would leave fewer than 80, stop and ask the user.
- Timeouts: 75 s request timeout; a retry after a timeout waits at least 15 s and resends identical params (never `no_cache`). A retry served from SerpApi's cache (original `created_at` older than the send time) is refunded.
- Used so far: 121 logged (8 smoke test and fixtures, 32 tuning, 50 held-out test, 2 post-fix top-up, 29 frozen v2); account had 126 left after v2. v2 is frozen: never edit eval/dataset_v2.jsonl or change code because of v2 results. Demo bundle and eval replay cost 0. Tune only on cached data. Client-side timeouts can be billed, which is why `SearchClient.credits_used` counts them.
- If `SERPAPI_API_KEY` is missing when a live run is needed, stop and tell the user exactly what to do.

## Approved amendments
- A1: eval "real" rows need a DOI or arXiv ID, validated against Crossref or arXiv by `eval/validate_dataset.py`. Rows that fail are dropped. Labels never come from GhostCite output.
- A2: `--demo` (CLI) and a web demo toggle run from `samples/demo_cache/`. Without a key, the web shows a banner and offers demo mode only. The README puts the zero-key path first.
- A3: web binds to 127.0.0.1 by default (warning on 0.0.0.0), with a per-job search cap, a global shared budget, a concurrent-job limit and a max-references limit, each with a clear error.
- A4: Account API preflight (refuse if searches left < estimate) plus a token-bucket pacer under the hourly limit.
- A5: separate Google organic parser. Fallback-only matches have a confidence cap and say so in the reason.
- A6: verify the gitleaks pre-commit hook on Windows; if it fails, use detect-secrets and document the choice.

## Checkpoints
At the end of each phase: all gates green, PROGRESS.md updated, then STOP and give a summary, the gate results and a ready-to-run conventional commit command. Wait for "continue".
1 skeleton/tooling/models/config · 2 ingest+parse · 3 search+live smoke · 4 match/verdict/reports/CLI · 5 web+Action · 6 eval · 7 docs/Docker/final verification.
