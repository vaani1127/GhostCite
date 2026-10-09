# How GhostCite was evaluated

This page explains how we measured GhostCite, which numbers to quote, and every failure on
the held-out sets. All numbers can be reproduced offline with no API key, from files in
the repository (see [Reproducing](#reproducing-the-numbers)).

There are three sets of results, and only the first is the headline:

1. **v2, a frozen held-out set (headline).** 26 new references that share no paper with
   v1. The set was frozen before any search and run exactly once, with the code frozen.
2. **v1 first held-out run (historical).** The first run on v1's test split. It was an
   honest held-out estimate when it was made.
3. **v1 post-fix rerun (not a held-out estimate).** v1 rerun after fixing bugs that the
   first run exposed. It shows the effect of the fixes and nothing more.

Every rate is given as counts with a 95% Wilson score interval, because the sets are
small. Per-type results with fewer than 5 rows are shown as counts only.

## Headline: frozen held-out set v2

### What was frozen, and how

* **Dataset:** `eval/dataset_v2.jsonl`, SHA-256
  `sha256:e7e752544795eeabbd24b2a66f94ccbef04660b4bc341a6d6d22a83cf8888604`. The hash was
  recorded here and in `eval/run.py` before any live search. `eval/run.py --dataset v2`
  refuses to run if the file changes.
* **Code:** commit `c8647d9`, plus only the changes made for this evaluation:
  * credit logging for every live run
  * the v2 options in the runner and validator
  * Wilson intervals in the reports
  * wider hygiene tests
  * LF line endings

  None of these touches parsing, search planning, matching or verdict logic.
* **Run:** exactly once, as raw strings (29 searches) and then as BibTeX (0 new
  searches, because the queries were cached). No code was changed in response to the
  results; the failures below are documented, not fixed.

### Results

Raw reference strings and BibTeX gave identical results.

| v2 (26 references) | Raw reference strings and BibTeX |
| --- | --- |
| **False alarms on real references** | **1/16 = 6.2% [1.1, 28.3]** |
| **Detection of fabricated references** | **8/10 = 80.0% [49.0, 94.3]** |
| Indian journals and books: false alarms | 0/7 = 0.0% [0.0, 35.4] |
| Indian journals and books: detection | 4/5 = 80.0% [37.6, 96.4] |
| Precision of "flagged" | 8/9 = 88.9% [56.5, 98.0] |
| Recall of "flagged" | 8/10 = 80.0% [49.0, 94.3] |
| F1 of "flagged" | 84.2% |
| Unchecked (unparseable or skipped) | 0 |

Detection per fabrication type (2 rows each, so counts only):

| Reworded title | Swapped authors | Wrong year (more than 1 off) | Fake venue | Fully invented |
| --- | --- | --- | --- | --- |
| 2/2 | 2/2 | 2/2 | **0/2** | 2/2 |

The full confusion matrix and per-class scores are in `eval/results_v2.md`.

### Every v2 failure, with its cause

| Row | Expected → got | Cause |
| --- | --- | --- |
| `soc-granovetter-1973` | VERIFIED → METADATA_MISMATCH | Google Scholar's cluster headline record for "The strength of weak ties" is a **1977 record** with venue "Social networks", most likely the reprint in Leinhardt's 1977 edited book. Its year and venue therefore disagree with the 1973 *American Journal of Sociology* article. The reason notes that Scholar lists 94 versions. This is the same reprint limitation as Akerlof in v1. |
| `fab-venue-myers` | METADATA_MISMATCH → VERIFIED | The real venue is ***Nature***, a one-word venue. GhostCite only judges a venue with at least two significant words, a guard that keeps acronyms such as "NeurIPS" vs "Advances in Neural Information Processing Systems" from becoming false alarms. The venue comparison was "unknown", so the fake venue "Global Ecology and Biogeography" passed unnoticed. |
| `fab-venue-gadagkar` | METADATA_MISMATCH → VERIFIED | Same cause: ***Journal of Biosciences*** reduces to one significant word ("journal" is treated as generic), so the fake "Indian Journal of Experimental Biology" was not judged. |

Neither bug was fixed: the freeze rules forbid changes based on v2. The fix is on the
roadmap: judge one-word venues when the cited venue is a multi-word name and neither side
looks like an acronym. It would need its own tuning on v1 and a fresh held-out check.

**What v2 tells us beyond v1:**
* The fixes for Scholar's new "bullet" summary layout held up on unseen papers. 11 of
  the 29 recorded first results used that layout, and none of the v2 failures came from
  parsing it.
* Fake venues remain the weakest type: 0/2 in v1's first held-out run, and 0/2 in v2 for
  a different reason.
* Both v2 misses involve venues that reduce to a single word. v1's fake-venue rows (2/2
  detected post-fix) all had multi-word real venues, so v1 could not show this.

### v2 composition

26 rows. All 26 passed validation against Crossref, so none were dropped. A test
(`tests/unit/test_eval_datasets.py`) enforces that v2 shares no DOI, title or row id with
v1.

* **16 real**
  * **9 international**, from fields v1 does not cover: psychology (Baron & Kenny),
    statistics (Benjamini & Hochberg; Dempster, Laird & Rubin), chemistry (Becke),
    ecology (Hardin; Myers et al.), earth science (Rockström et al.), materials (Novoselov
    et al.) and sociology (Granovetter).
  * **7 Indian**
    * 6 articles in Indian journals: *Indian Journal of Anaesthesia*, *Indian Journal of
      Psychological Medicine*, *Journal of Ayurveda and Integrative Medicine*, *Mausam*,
      *Bulletin of Materials Science* and *Journal of Biosciences*.
    * 1 book by Indian authors: Drèze & Sen, *An Uncertain Glory*, Princeton University
      Press.
* **10 fabricated**, 2 of each type, 5 of them from Indian rows:
  * 8 perturbations of v2 real rows
  * 2 fully invented references

## Historical: v1 first held-out run

This was the first and only run on v1's test split before any change informed by it
(`eval/results_heldout_first_run.md`). It was the held-out estimate until v2 replaced it.

| v1 test split (39 references) | Raw reference strings | BibTeX |
| --- | --- | --- |
| False alarms on real references | 6/28 = 21.4% [10.2, 39.5] | 5/28 = 17.9% [7.9, 35.6] |
| Detection of fabricated references | 8/11 = 72.7% [43.4, 90.3] | 8/11 = 72.7% [43.4, 90.3] |
| Indian subset: false alarms | 3/13 = 23.1% [8.2, 50.3] | 2/13 = 15.4% [4.3, 42.2] |
| Indian subset: detection | 4/5 = 80.0% [37.6, 96.4] | 4/5 = 80.0% [37.6, 96.4] |
| Precision of "flagged" | 8/14 = 57.1% [32.6, 78.6] | 8/13 = 61.5% [35.5, 82.3] |
| Recall of "flagged" | 8/11 = 72.7% [43.4, 90.3] | 8/11 = 72.7% [43.4, 90.3] |

Per type (raw strings, counts only): reworded title 2/2, swapped authors 2/2, wrong year
2/3, fake venue 0/2, invented 2/2.

## v1 post-fix rerun: not a held-out estimate

The first v1 test run exposed five bugs, mostly caused by Google Scholar changing its
result layout on the day of the run (details [below](#every-failure-on-the-v1-test-split)).
After they were fixed, a rerun of the same rows gave:

| v1 post-fix rerun, test split | Raw strings and BibTeX (identical) |
| --- | --- |
| False alarms | 1/28 = 3.6% [0.6, 17.7] |
| Detection | 11/11 = 100% [74.1, 100.0] |
| Indian subset | 0/13 false alarms [0.0, 22.8]; 5/5 detected [56.6, 100.0] |
| Precision / recall of "flagged" | 11/12 = 91.7% [64.6, 98.5] / 11/11 |

**These numbers are optimistic and must not be quoted as an estimate.** We looked at the
test split to find the bugs. v2 exists to measure the fixed code honestly.

## Method

### Ground truth that does not depend on GhostCite

Labels never come from GhostCite's output, and validation never uses SerpApi.

* Every **real** row has a DOI or an arXiv ID. `eval/validate_dataset.py` resolves each
  one with the Crossref REST API or the arXiv API. A row passes only if the title, the
  first author's surname and the year (within ±1 for online-first dates) match.
* Every **perturbed** row is built from a validated real row by changing exactly one
  thing, which its `perturbation` field records:
  * a reworded title
  * swapped or replaced authors
  * a year more than one year off
  * a venue the paper never appeared in
* Each **fully invented** row passes only if Crossref's bibliographic search finds no
  work with a similar title (similarity below 0.8). For v2's two invented rows the
  closest Crossref titles scored 0.63 and 0.56.

`eval/run.py` refuses to run on rows that have not been validated.

Expected verdicts:
* Real rows: VERIFIED.
* Perturbed rows: METADATA_MISMATCH.
* Invented rows: NOT_FOUND.

The headline metrics count *any* flag (METADATA_MISMATCH or NOT_FOUND) on a fabricated
row as a detection. Exact class agreement is reported separately in `eval/results*.md`.

### v1 dataset and its tuning/test split

`eval/dataset.jsonl` has 67 rows: 47 real and 20 fabricated, 4 of each type. All 67
passed validation.

| v1 | CS | Medicine | Economics | Science | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Real, international journals | 10 | 9 | 9 | 0 | 28 |
| Real, Indian journals and books | 2 | 4 | 6 | 7 | 19 |
| Fabricated | 7 | 6 | 6 | 1 | 20 |

The Indian subset of v1 has:
* 11 articles in Indian journals: *Sadhana*, *Pramana*, *Current Science*, *Indian Journal
  of Psychiatry*, *Indian Pediatrics*, *Vikalpa*, *IIMB Management Review* and *Journal of
  Postgraduate Medicine*.
* 4 classic papers by Indian authors in international journals: Raman, Bose, Chandrasekhar
  and Sen.
* 4 books.

`ghostcite.evaluation.split` makes a fixed-seed (20261009) stratified split of about
40/60: 28 rows for tuning and 39 for testing.
* It splits by **family**: a real row and every fabrication made from it land in the same
  split.
* Families are stratified by type and by field.
* All five Indian fabrications fell into the test split, so nothing about them was tuned.

Thresholds and rules were changed only after looking at the tuning split.

### Input formats

Each row is rendered as a raw reference string in one of four styles, assigned round-robin
with a fixed seed:
* APA
* IEEE
* Vancouver
* the style common in Indian commerce and management journals: `Surname, I.K. and
  Surname, I.K. (Year), "Title", Journal, Vol. X No. Y, pp. a-b.`

The strings go through the full pipeline: splitting, field parsing, search, matching and
verdict. The **same rows are also run as BibTeX**, which separates parsing errors from
matching errors. The BibTeX run reuses the text run's cached searches, so it costs
almost nothing.

### Metrics

* **False alarm rate**: real references that GhostCite flagged, divided by the real
  references.
* **Detection rate**: fabricated references that GhostCite flagged, divided by the
  fabricated references.
* **Precision, recall and F1** for "flagged", and per class for NOT_FOUND and
  METADATA_MISMATCH. Precision and recall are given with their counts. The full confusion
  matrix is in `eval/results*.md`.
* **Unchecked**: rows that came back UNPARSEABLE or SKIPPED_BUDGET. Zero in every run.
* **Intervals**: 95% Wilson score intervals (`ghostcite.evaluation.report.wilson`).

## v1 tuning log (tuning split only)

1. **Dedupe on all fields.** Two references with the same title but a different venue
   were merged, so a fabricated venue inherited the real one's verdict.
2. **Confident stop.** The planner stops searching only when the best candidate is a
   title match with no field disagreement.
3. **Books and editions.** For `book` entries, a year difference is a partial match
   (editions differ), and a publisher is never a venue mismatch.
4. **Venue comparison.** Token-sort similarity plus abbreviation overlap that must align
   from the first word.
5. **Publisher-only venues.** A reference whose venue is only a publisher is treated as a
   book.
6. **Comma-style titles.** In comma-separated styles, the title ends at the comma after
   the year.
7. **Middle band and versions.** Added at Checkpoint 5 and checked on the tuning split.

No similarity threshold was lowered to fix a false alarm. `tests/unit/test_title_variants.py`
checks that harmless title differences still VERIFY:
* a dropped subtitle
* Scholar's "…" truncation
* hyphenation and spacing
* British vs American spelling
* "2" vs "two"
* LaTeX and curly-quote leftovers

## Every failure on the v1 test split

### First held-out run

Raw reference strings: 6 false alarms, 3 missed fabrications and 1 class difference.

| Row | Expected → got | Cause | Fixed? |
| --- | --- | --- | --- |
| `eco-akerlof-1970` | VERIFIED → METADATA_MISMATCH | Scholar's cluster headline record for "The market for lemons" is a **1978 reprint**, so the year disagrees. | No (limitation) |
| `eco-davis-1989` | VERIFIED → METADATA_MISMATCH | Google Scholar switched to a **new summary layout** on the day of the run, gluing author and venue together with a `•` before the source (`FD DavisMIS quarterly, 1989•JSTOR`). The parser read the whole string as the author. | Yes: bullet-layout parser |
| `in-bose-1924` | VERIFIED → METADATA_MISMATCH | Same layout change. | Yes |
| `in-surappa-2003` | VERIFIED → METADATA_MISMATCH | Same layout change. | Yes |
| `fab-venue-arun` | METADATA_MISMATCH → VERIFIED | Same layout change: the venue was not parsed. | Yes |
| `fab-venue-fama` | METADATA_MISMATCH → VERIFIED | Same as above. | Yes |
| `fab-year-huang` | METADATA_MISMATCH → VERIFIED | Same layout change: the year was not parsed. | Yes |
| `in-bhagwati-1993` | VERIFIED → NOT_FOUND | IEEE-style book citation: the title was cut at the wrong comma. | Yes |
| `med-livak-2001` | VERIFIED → METADATA_MISMATCH | Scholar writes "ΔΔCT" with separated letters, so the title words differed. | Yes: single-letter runs are merged |
| `fab-authors-livak` (class difference) | METADATA_MISMATCH → NOT_FOUND | Same title-word problem; still detected. | Yes |

BibTeX had the same failures except `in-bhagwati-1993`, a parsing problem that BibTeX's
structured fields avoid.

### Post-fix rerun

* Test split: `eco-akerlof-1970` (the 1978 reprint).
* Tuning split:
  * `eco-markowitz-1952`: Scholar's headline record is a 1955 version.
  * `eco-jensen-1976`: Scholar ranks a 2019 reprint in an edited book above the 1976
    article. This row was VERIFIED in the first tuning run, so it is a regression.
  * Class difference: `fab-reword-breiman` came back NOT_FOUND.

## Limitations

* **Reprints of classic papers.** For some famous papers, Scholar's cluster headline is a
  later reprint (Akerlof, Markowitz, Jensen and, in v2, Granovetter). GhostCite then
  reports a year or venue mismatch and adds "Google Scholar lists this work with N
  versions; this may be a different version." We rejected a reprint-tolerance rule
  because it would have hidden two of v1's four wrong-year fabrications.
* **One-word venues.** A fake venue goes undetected when the real venue reduces to one
  significant word, such as *Nature*, *Science*, *Cell* or *Journal of Biosciences*. This
  caused both v2 misses.
* **Small samples.** v2 has 16 real and 10 fabricated rows, so the intervals are wide.
  The 80% detection rate could plausibly be anywhere from about 49% to 94%. The results
  show which kinds of error GhostCite makes, not precise rates.
* **Single-field perturbations.** LLM hallucinations often change several fields at once.
  Those are usually easier to catch, so these detection rates are likely conservative.
* **Scholar changes.** A layout change can silently break parsing. The bullet-layout
  fixtures guard against that one change, not against future ones.
* **Coverage.** Old books, theses and regional journals that Scholar does not index can
  come back NOT_FOUND even when they are real. NOT_FOUND means "not found here", never
  "proven fake".

## Credits used

Every live run appends its search count to the credits log: CLI, web UI and evaluation
alike. Lines contain counts only, never the key or query text. The log is
`.dev/credits.log` in a development checkout (gitignored), otherwise `credits.log` next to
the cache, or wherever `GHOSTCITE_CREDITS_LOG` points.

| Run | Searches |
| --- | ---: |
| Checkpoint 3 smoke test and fixtures (one timed-out request was still billed) | 8 |
| v1 tuning split, first live run and top-up | 32 |
| v1 test split, first held-out run (text 49 + BibTeX 1) | 50 |
| v1 post-fix rerun top-up | 2 |
| v2 frozen held-out run (estimate 39, cap 40; text 29 + BibTeX 0) | 29 |
| **Project total** | **121 / 150 cap** |

After the v2 run the account had 126 searches left, above the required 80. The account
balance fell from 155 to 126, exactly the 29 searches the log recorded.

## Reproducing the numbers

```bash
# Free, no API key: replay the recorded responses
python eval/run.py --dataset v2        # 29 responses in eval/responses_v2.json
python eval/run.py                     # v1: 79 responses in eval/responses.json

python eval/validate_dataset.py --dataset v2   # re-check ground truth (Crossref/arXiv, free)

# With a key (spends searches; refuses if the estimate exceeds --max-searches or the
# account would keep fewer than --reserve searches)
python eval/run.py --dataset v2 --live --max-searches 40 --reserve 80
python eval/run.py --dataset v2 --record   # rebuild the replay file from the local cache
```

The replay files contain each response the evaluation read. They are trimmed to the
fields GhostCite parses and sanitized: no API key, no account links and no e-mail
addresses, which `tests/unit/test_fixture_hygiene.py` enforces. Replaying them reproduces
the v2 tables and the v1 post-fix tables exactly. `eval/results_heldout_first_run.*`
preserve the first v1 held-out run as produced. A replay rewrites `eval/results*.json` with
`mode: replay` and 0 searches; the committed v2 files keep the live run's mode and search
count.
