# Submission form text (SerpApi India Hackathon 2026)

Ready-to-paste answers for each form field. Fields marked *[fill in the form directly]*
contain personal details, which must never be committed to this repository.

---

**Participant / team details:** *[fill in the form directly]*

**Where did you hear about the hackathon (community source):** *[fill in the form directly]*

**Project name:** GhostCite

**Track:** Knowledge & Public Interest

**Did the project exist before the hackathon?** No. It was built from scratch during the
hackathon.

**Repository:** https://github.com/vaani1127/GhostCite

**Demo video:** *[paste the unlisted video link]*

**Hosted demo:** https://ghostcite.vaaniprashar.tech. It runs in demo mode only with
recorded Google Scholar responses, so it never spends search credits. The first load can
take about a minute because the free instance sleeps when idle. Live checks need a local
run with your own SerpApi key (see the README).

---

### One-line summary

GhostCite catches hallucinated and wrong academic citations by checking every reference
against live Google Scholar data through SerpApi, and explains each verdict in one plain
sentence.

### Project description

Language models now help write papers, theses and reports, and they invent citations:
real-sounding titles that do not exist, real papers with the wrong year, venue or
authors. Checking a reference list by hand takes hours, so most reviewers don't.

GhostCite takes a PDF, a BibTeX file or a pasted reference list. It parses each reference
in common styles (APA, IEEE, Vancouver and Indian journal styles), searches Google
Scholar through SerpApi, and compares the title, authors, year and venue with what
Scholar actually lists. Every reference gets a verdict with a reason, for example:
* **Verified**
* **Metadata mismatch**: "Title matches, but year is 2015, not 2019"
* **Not found**

The document gets an integrity score. There is no AI in the checking itself: verdicts are
deterministic, reproducible and explainable.

It runs as:
* a command-line tool, with JSON, Markdown, HTML and SARIF reports, and a `--fail-on`
  exit code for CI
* a local web UI with live progress and a summary card
* a GitHub Action that turns bad citations into code-scanning alerts on the exact line
  of a .bib file

A zero-key demo mode lets anyone try it in 30 seconds.

We evaluated it on a frozen held-out set of 26 references validated against Crossref,
in fields and journals it was never tuned on:
* **1/16 false alarms** on real references
* **8/10 fabricated references detected**, including Indian journals and books

We publish confidence intervals and every failure, including the two kinds of error it
still makes.

### Who it helps

* **Reviewers, editors and examiners**: they can screen a manuscript's references in
  seconds and spend their time on the flagged ones.
* **Students and researchers**: they can check their own bibliography before submission,
  especially when an AI assistant helped draft it.
* **Universities and journals in India**: the parser handles Indian citation styles and
  name orders, the Google fallback is localised (`gl=in`), and Indian journals and books
  are part of the evaluation (0/7 false alarms, 4/5 fabrications detected).
* **The public**: fabricated references that slip into policy reports, news and
  Wikipedia erode trust in research. GhostCite makes checking cheap enough to do every
  time.

### How we use SerpApi, and why it matters

SerpApi is the core of GhostCite. Without structured, live Google Scholar data there is
no ground truth to check a citation against.

* **Google Scholar API (primary).** A two-step plan per reference:
  1. Search the exact title in quotes.
  2. If needed, search the title plus `author:"surname"`.

  We parse the title, authors, venue, year, "cited by" and number of versions from the
  organic results. We even handled a change in Scholar's result layout that appeared
  during our evaluation.
* **Google Search API (fallback).** For books, theses and reports that Scholar indexes
  poorly, we read the Knowledge Graph (`gl=in`, `hl=en`). Matches found this way are
  clearly labelled and capped in confidence.
* **Account API.** A free preflight check refuses a run the account cannot afford, and
  live calls are paced below the hourly limit. Only counts are read from it; the key and
  e-mail in the response are never stored.
* **Cost discipline.**
  * Results are cached locally, and duplicates are searched once.
  * Timeouts are retried in a way that reuses SerpApi's own one-hour cache instead of
    paying twice.
  * Every live run has a hard cap and is logged.
  * In our frozen evaluation, 26 references cost 29 searches.

### Built with AI tools

We used **Claude Code** (Anthropic) as a coding assistant. It helped:
* write the code and the tests
* design the evaluation harness
* find bugs, including Scholar's layout change, which it traced from the evaluation
  failures to recorded responses

We built the project in seven checkpoints. At each one a human reviewed the code, the
test and quality-gate results and the evaluation before approving the next step. The
humans set the evaluation rules: Crossref-validated ground truth, a held-out split, a
frozen v2 set and honest reporting of failures. GhostCite itself uses no AI at run time.

### Tech stack

Python 3.11+, the official `serpapi` client, pydantic, pypdf, bibtexparser, rapidfuzz,
Typer and Rich, FastAPI and Uvicorn, Jinja2. Tests use pytest, Hypothesis and
pytest-socket (no network in tests), with 99% coverage; types are checked with
`mypy --strict`. Docker, a GitHub Action, Apache-2.0.
