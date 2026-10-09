## What and why

<!-- One or two sentences. Link the issue if there is one. -->

## Checklist

- [ ] `python tasks.py check` passes (ruff, format, mypy --strict, tests with coverage of 90% or more)
- [ ] Tests added or updated; no test uses the network
- [ ] No key, SerpApi URL, e-mail address or other personal data in code, fixtures or this PR
- [ ] If parsing, planning, matching or verdict rules changed: checked on the v1 tuning split only, and `eval/dataset_v2.jsonl` is untouched
- [ ] No live SerpApi searches were needed, or the count is stated here: ___
- [ ] `CHANGELOG.md` updated under "Unreleased"
