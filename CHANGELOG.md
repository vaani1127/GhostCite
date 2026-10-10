# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Hosted demo mode (`GHOSTCITE_HOSTED_DEMO=true`): the server refuses every live check with
  HTTP 403, and the UI selects Demo, disables Live with a hint and says it is a hosted copy.
- `render.yaml` Blueprint for a demo-only deployment on Render's free tier, with no SerpApi key.
- The container listens on `PORT` when set (else 8000); the progress stream sends
  keep-alive comments and disables proxy buffering.

## [0.1.0] - 2026-10-10

First release, built for the SerpApi India Hackathon 2026 (Knowledge & Public Interest).

### Added

#### Input
- PDF (one or two columns, references section detection), BibTeX and pasted text.
- Citation styles: APA, IEEE, Vancouver and Indian journal styles, including Indian name
  orders.

#### Search (SerpApi)
- Google Scholar first: an exact-title search, then title plus author.
- Google Search fallback with the Knowledge Graph for books, theses and reports.
- Account API preflight that refuses runs the account cannot afford, and pacing below the
  hourly limit.
- Local SQLite cache, hard search budgets, and timeout retries that reuse SerpApi's own
  cache.

#### Matching and verdicts
- Title matching that tolerates truncation, dropped subtitles, hyphenation and spelling
  variants.
- Author, year and venue comparison.
- Verdicts: Verified, Metadata mismatch, Not found, Unparseable and Skipped, each with a
  one-line reason.
- Reworded-title detection that names the real paper, and a note when Scholar lists
  several versions of a work.
- Integrity score.

#### Reports and front ends
- Reports: terminal table, JSON, Markdown, self-contained HTML and SARIF 2.1.0.
- CLI (`check`, `web`, `cache`) with `--fail-on` exit codes.
- Local web UI on 127.0.0.1:
  - Server-Sent Events progress, a summary card, and light and dark themes.
  - Limits on upload size, references, concurrent jobs and searches.
- Zero-key demo mode (CLI and web) backed by recorded, sanitized responses.
- GitHub Action that uploads SARIF to code scanning.
- Docker image (slim, non-root) and `compose.yaml` that publishes on localhost only.
- Credits log of every live run (counts only).

#### Evaluation
- v1: 67 Crossref/arXiv-validated references, with a tuning/test split.
- v2: a frozen held-out set of 26 references.
- Wilson intervals, and replay files that reproduce every number without a key.

### Fixed during evaluation
- Parsing of Google Scholar's new "bullet" summary layout, where the author list is glued
  to the venue.
- IEEE-style book citations, and titles whose letters are separated in Scholar
  (e.g. "Δ Δ C T").

### Known limitations
- Fake venues are missed when the real venue is a single word (e.g. *Nature*).
- Classic papers whose main Scholar record is a later reprint can be flagged as
  wrong-year.

[Unreleased]: https://github.com/vaani1127/GhostCite/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/vaani1127/GhostCite/releases/tag/v0.1.0
