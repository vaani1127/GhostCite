# Contributing to GhostCite

Thanks for helping! Bug reports, new citation styles, parser fixtures and documentation
fixes are all welcome.

## Set up

```bash
git clone https://github.com/vaani1127/GhostCite.git
cd GhostCite
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
python tasks.py check
```

`tasks.py check` runs everything CI runs:
* `ruff check`
* `ruff format --check`
* `mypy --strict`
* pytest, with at least 90% coverage

You don't need a SerpApi key to develop: tests never touch the network, which
`pytest-socket` enforces, and they use recorded responses in `tests/fixtures/`.

## Ground rules

* **No secrets, ever.** Put your key only in `.env`, which is gitignored. Never paste a
  key, a full SerpApi URL or an e-mail address into code, tests, fixtures or issues.
  * Recorded responses must go through `ghostcite.search.sanitize`
    (`scripts/record_fixtures.py` does this).
  * `tests/unit/test_fixture_hygiene.py` fails on key-shaped strings, e-mail addresses
    and SerpApi archive links in `eval/`, `samples/` and `tests/fixtures/`.
* **Secret scanning.** The pre-commit hooks include
  [gitleaks](https://github.com/gitleaks/gitleaks) with a SerpApi key rule in
  `.gitleaks.toml`.
  * On Windows, pre-commit builds gitleaks with Go on first install, which takes a minute.
  * A fake key that a test genuinely needs gets a narrow inline `# gitleaks:allow`
    comment on that exact line. Never loosen `.gitleaks.toml` instead.
  * CI scans the full history too.
* **Deterministic and explainable.** Every verdict must come with a reason a reviewer can
  check. Don't add models or randomness to the pipeline.
* **Thresholds live in `src/ghostcite/config.py`**, each with a comment saying why.
* **Evaluation honesty.**
  * Changes to parsing, planning, matching or verdict rules must be judged on the v1
    tuning split. Never judge them on a held-out set.
  * Never edit `eval/dataset_v2.jsonl`: its hash is frozen.
  * A new held-out set is needed before claiming improved numbers.
* **Spending credits.** Live runs always need an explicit `--max-searches` and are logged
  in the credits log. Prefer `--offline`, `--demo` and the replay files.

## Adding a parser fixture

1. Reproduce the problem with a reference string in a unit test.
2. If Scholar's response matters, record it once with `scripts/record_fixtures.py`
   (this spends a search). Commit the sanitized JSON under `tests/fixtures/serpapi/`.
3. Add a test that fails before your fix and passes after.

## Pull requests

* Keep each PR focused, and include tests.
* Use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages,
  e.g. `fix(parse): keep Indian initials after the surname`.
* Update `CHANGELOG.md` under "Unreleased".
* By contributing you agree that your work is licensed under Apache-2.0.

Please follow our [Code of Conduct](CODE_OF_CONDUCT.md).
