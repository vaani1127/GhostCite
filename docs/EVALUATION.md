# How GhostCite was evaluated

This page explains how we measured GhostCite, which numbers to quote, and everything
that went wrong on the held-out set. Every number here can be reproduced offline, with no
API key, from files in the repository (see [Reproducing](#reproducing-the-numbers)).

## The numbers to quote

These come from the **first and only run on the held-out test split made before any
change informed by it** (`eval/results_heldout_first_run.md`). Brackets show 95% Wilson
score intervals, because the sets are small.

| Test split (39 references) | Raw reference strings | BibTeX |
| --- | --- | --- |
| False alarm rate on real references | **6/28 = 21.4%** [10.2, 39.5] | 5/28 = 17.9% [7.9, 35.6] |
| Detection rate on fabricated references | **8/11 = 72.7%** [43.4, 90.3] | 8/11 = 72.7% [43.4, 90.3] |
| Precision / recall / F1 for "flagged" | 57.1% / 72.7% / 64.0% | 61.5% / 72.7% / 66.7% |
| Indian journals and books: false alarms | 3/13 = 23.1% [8.2, 50.3] | 2/13 = 15.4% |
| Indian journals and books: detection | 4/5 = 80.0% [37.6, 96.4] | 4/5 = 80.0% |

Detection rate per perturbation type (raw strings, first test run):

| Perturbation | Detected |
| --- | --- |
| Reworded title | 2/2 |
| Swapped authors | 2/2 |
| Wrong year (more than 1 off) | 2/3 |
| Fake venue | 0/2 |
| Fully invented | 2/2 |

Reading the first run's failures exposed five bugs, most of them caused by Google Scholar
changing its result layout on the day of the run (details [below](#every-failure-on-the-test-split)).
After fixing them, a **post-fix rerun** of the same rows gives:

| Post-fix rerun, test split | Raw strings and BibTeX (identical) |
| --- | --- |
| False alarm rate | 1/28 = 3.6% [0.6, 17.7] |
| Detection rate | 11/11 = 100% [74.1, 100] |
| Indian subset | 0/13 false alarms, 5/5 detected |
| Precision / recall / F1 for "flagged" | 91.7% / 100% / 95.7% |

**The post-fix numbers are not a held-out estimate.** We looked at the test split to find
those bugs, so the rerun is optimistic. We report it only to show the effect of the
fixes. A fresh held-out set would be needed for an unbiased post-fix estimate; we did not
have the budget to build one before the deadline.

## Method

### Dataset

`eval/dataset.jsonl` has 67 rows: 47 real references and 20 fabricated ones.

| | CS | Medicine | Economics | Science | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Real, international journals | 10 | 9 | 9 | 0 | 28 |
| Real, Indian journals and books | 2 | 4 | 6 | 7 | 19 |
| Fabricated | 7 | 6 | 6 | 1 | 20 |

The real rows are well-known papers across the three fields, plus a 19-row Indian subset:
* 11 articles in Indian journals (*Sadhana*, *Pramana*, *Current Science*, *Indian Journal of
  Psychiatry*, *Indian Pediatrics*, *Vikalpa*, *IIMB Management Review*, *Journal of
  Postgraduate Medicine*)
* 4 classic papers by Indian authors in international journals (Raman, Bose,
  Chandrasekhar, Sen)
* 4 books from Indian authors (Sen, Bhagwati, Rao, Chockalingam)

### Ground truth that does not depend on GhostCite

Labels never come from GhostCite's output, and validation never uses SerpApi.

* Every **real** row has a DOI (45 rows) or an arXiv ID (2 rows).
  `eval/validate_dataset.py` resolves each one with the Crossref REST API or the arXiv
  API. A row passes only if the title, the first author's surname and the year (within ±1
  for online-first dates) match.
* Every **fabricated** row is built from a validated real row by changing exactly one
  thing, which its `perturbation` field records:
  * a reworded title
  * swapped or replaced authors
  * a year more than one year off
  * a venue the paper never appeared in
* Each **fully invented** row passes only if Crossref's bibliographic search finds no
  work with a similar title (similarity below 0.8).

All 67 rows passed. None were dropped, and `eval/dataset_validation.json` records the
canonical metadata found for each row. `eval/run.py` refuses to run on unvalidated rows.

Expected verdicts:
* Real rows: VERIFIED.
* Perturbed rows: METADATA_MISMATCH. A reworded title should be matched to the real
  paper through the middle band.
* Invented rows: NOT_FOUND.

The headline metrics deliberately treat *any* flag (METADATA_MISMATCH or NOT_FOUND) on a
fabricated row as a detection. Exact class agreement is reported separately.

### Tuning/test split

`ghostcite.evaluation.split` makes a fixed-seed (20261009) stratified split of about 40/60:
28 rows for tuning and 39 for testing. It splits by **family**, so a real row and every
fabrication made from it always land in the same split, and the test set never contains
a perturbation of a paper that was tuned on. Families are stratified by type (real only,
real with perturbations, invented) and by field.

One consequence of splitting by family: all five Indian fabrications fell into the test
split, so the tuning split has no Indian fabrications. Nothing about Indian fabrications
was tuned.

Thresholds and rules were changed **only after looking at the tuning split**. The test
split was run once, and those numbers are the ones above.

### Input formats

Real papers are cited in many styles, so each row is rendered as a raw reference string
in one of four styles, assigned round-robin with a fixed seed:

* APA
* IEEE
* Vancouver
* the Indian commerce/management journal style: `Surname, I.K. and Surname, I.K. (Year), "Title", Journal, Vol. X No. Y, pp. a-b.`

The strings go through the full pipeline: splitting, field parsing, search, matching and
verdict. The **same rows are also run as BibTeX**, which separates parsing errors from
matching errors. In practice the BibTeX run shares its searches with the text run through
the cache, which is why it costs almost nothing.

### Metrics

* **False alarm rate**: real references that GhostCite flagged (METADATA_MISMATCH or
  NOT_FOUND), divided by the real references.
* **Detection rate**: fabricated references that GhostCite flagged, divided by the
  fabricated references.
* **Precision, recall and F1** for "flagged", plus per class for NOT_FOUND and
  METADATA_MISMATCH. Also the full confusion matrix (expected × predicted). See
  `eval/results*.md`.
* **Unchecked**: rows that came back UNPARSEABLE or SKIPPED_BUDGET. Zero in every run.
* The intervals are 95% Wilson score intervals.

## Tuning log (tuning split only)

Every change below was made after reading the tuning split's results. None of them came
from test-split rows.

1. **Dedupe on all fields.** Two references with the same title but a different venue
   were merged, so a fabricated venue inherited the real one's verdict.
2. **Confident stop.** The planner now stops searching only when the best candidate is a
   title match with no field disagreement. Before, a title-only match stopped early and
   missed a better record on the next query.
3. **Books and editions.** For `book` entries, any year difference is a partial match,
   because editions differ, and a publisher name is never a venue mismatch.
4. **Venue comparison.** Token-sort similarity plus abbreviation overlap that must align
   from the first word. Abbreviated journal names still match their full names, and two
   different journals that share a long common prefix do not.
5. **Publisher-only venues.** A reference whose venue is only a publisher is treated as a
   book.
6. **Comma-style titles.** In comma-separated styles, the title ends at the comma after
   the year.
7. **Middle band and versions.** These were added at Checkpoint 5 and checked on the
   tuning split. A reworded title within the band (with matching first author and
   year ±1) becomes METADATA_MISMATCH, naming the real paper's title. A title match that
   disagrees on year or venue says how many versions Scholar lists.

No similarity threshold was lowered to fix a false alarm. A separate test suite
(`tests/unit/test_title_variants.py`) checks that common harmless title differences still
VERIFY:
* a dropped subtitle
* Scholar's "…" truncation
* hyphenation and spacing
* British vs American spelling
* "2" vs "two"
* LaTeX and curly-quote leftovers

## Every failure on the test split

### First held-out run (the quoted numbers)

Raw reference strings: 6 false alarms, 3 missed fabrications and 1 class difference.

| Row | Expected → got | Cause | Fixed? |
| --- | --- | --- | --- |
| `eco-akerlof-1970` | VERIFIED → METADATA_MISMATCH | Scholar's cluster headline record for "The market for lemons" is a **1978 reprint**, so the year disagrees (1978 vs 1970). Scholar lists 46 versions, and the reason says so. | No (limitation, see below) |
| `eco-davis-1989` | VERIFIED → METADATA_MISMATCH | Google Scholar switched to a **new summary layout** on the day of the run: author and venue are glued together with a `•` before the source (`FD DavisMIS quarterly, 1989•JSTOR`). The parser read the whole string as the author. | Yes: bullet-layout parser that uses Scholar's structured author list |
| `in-bose-1924` | VERIFIED → METADATA_MISMATCH | Same layout change (`BoseZeitschrift für Physik, 1924•Springer`). | Yes |
| `in-surappa-2003` | VERIFIED → METADATA_MISMATCH | Same layout change (`MK SurappaSadhana, 2003•Springer`). | Yes |
| `fab-venue-arun` | METADATA_MISMATCH → VERIFIED | Same layout change: the venue was not parsed, so the fake venue could not disagree with anything. | Yes |
| `fab-venue-fama` | METADATA_MISMATCH → VERIFIED | Same as above. | Yes |
| `fab-year-huang` | METADATA_MISMATCH → VERIFIED | Same layout change: the year was not parsed from the glued summary. | Yes |
| `in-bhagwati-1993` | VERIFIED → NOT_FOUND | An IEEE-style **book** citation. The parser cut the title at the wrong comma, and the closest result, "India in transition: Freeing the economy", scored only 88%. | Yes: the author list no longer ends early at a book-style comma |
| `med-livak-2001` | VERIFIED → METADATA_MISMATCH | The title contains "2^−ΔΔCT", and Scholar renders it with the letters separated ("Δ Δ C T"), so the title words did not match. | Yes: runs of single letters are merged before comparing |
| `fab-authors-livak` (class difference) | METADATA_MISMATCH → NOT_FOUND | Same title-word problem. It was still detected, so it is not a failure, just the wrong class. | Yes |

BibTeX: the same list minus `in-bhagwati-1993`, because BibTeX fields need no parsing.
That gives 5 false alarms and 3 misses.

Six of the nine failures came from the Scholar layout change, not from the matching
rules. Those references are covered now by three recorded fixtures in the new layout
(`tests/fixtures/serpapi/*bullet*.json`), with tests.

### Post-fix rerun (not a held-out estimate)

* Test split: one failure. `eco-akerlof-1970`, as above: the 1978 reprint.
* Tuning split, for completeness:
  * `eco-markowitz-1952`: Scholar's headline record is a 1955 version of "Portfolio
    selection".
  * `eco-jensen-1976`: Scholar ranks a 2019 reprint in an edited book, *Corporate
    governance*, above the 1976 *Journal of Financial Economics* article. This one was
    VERIFIED in the first tuning run and became a false alarm after the fixes, so we list
    it as a regression.
  * Class difference: `fab-reword-breiman` came back NOT_FOUND instead of
    METADATA_MISMATCH. The reworded title is far enough from the original that Scholar
    returned no related paper, so NOT_FOUND is a fair verdict for a reference nobody can
    find.

## Limitations

* **Reprints of classic papers.** Scholar's cluster headline for some famous papers is a
  later reprint (Akerlof, Markowitz, Jensen), so GhostCite reports a year or venue
  mismatch. It adds "Google Scholar lists this work with N versions; this may be a
  different version." We considered a rule to tolerate reprints and rejected it: it would
  have hidden two of the dataset's four wrong-year fabrications. In practice
  this is a false alarm a human resolves in seconds, and the reason text points to it.
* **Small sample.** 39 test rows give wide intervals (see the brackets above). The numbers
  show the error *types* GhostCite makes; they are not precise rates.
* **Fabrications are single-field perturbations.** LLM hallucinations often change
  several fields at once. Those are usually easier to catch, so these detection rates are
  likely conservative.
* **Scholar changes.** The first run showed that a layout change can silently break
  parsing. The bullet-layout fixtures and tests guard against this specific change, not
  against future ones.
* **Coverage.** Very old books, theses and regional journals that Scholar does not index
  can come back NOT_FOUND even when they are real. NOT_FOUND always means "not found
  here", never "proven fake".

## Credits used

All SerpApi usage is logged (counts only) in `.dev/credits.log`. The log is gitignored
because it is local.

| Run | Searches |
| --- | ---: |
| Checkpoint 3 smoke test and fixtures (one timed-out request was still billed) | 8 |
| Tuning split, first live run and top-up | 32 |
| Test split, held-out run (text 49 + BibTeX 1) | 50 |
| Post-fix rerun top-up (both splits) | 2 |
| **Project total** | **92 / 150 cap** |

The SerpApi account still had 155 searches after the last run. That is more than the
80-search reserve the project required.

## Reproducing the numbers

```bash
# Free, no API key: replays the 79 recorded responses in eval/responses.json
python eval/run.py                     # writes eval/results.json and eval/results.md

python eval/run.py --split test        # one split only
python eval/validate_dataset.py        # re-check the ground truth against Crossref/arXiv (free)

# With a key (spends searches; refuses to start if fewer than --reserve would remain)
python eval/run.py --live --split tuning --max-searches 60 --reserve 80
python eval/run.py --cache             # rerun from your local SQLite cache
python eval/run.py --record            # rebuild eval/responses.json from that cache
```

`eval/responses.json` holds each response the evaluation read. The responses are trimmed
to the fields GhostCite parses and sanitized: no API key, no links into the account's
search archive. Replaying them reproduces the post-fix tables exactly.
`eval/results_heldout_first_run.json` and `.md` preserve the first held-out run as it was
produced.
