# GhostCite evaluation results

Dataset: 67 validated references (0 dropped by validation). Split seed 20261009. Thresholds were tuned on the tuning split only.

**This is the held-out estimate**: the first and only run on the test split made before any change informed by it. Quote these test-split numbers.

### Test split, raw reference strings

39 references, 49 live searches in this run.

| Subset | Real | False alarms | False alarm rate | Fabricated | Detected | Detection rate | Unchecked |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All | 28 | 6 | 21.4% | 11 | 8 | 72.7% | 0 |
| Indian journals and books | 13 | 3 | 23.1% | 5 | 4 | 80.0% | 0 |

| Perturbation | Rows | Detected | Detection rate |
| --- | ---: | ---: | ---: |
| reworded title | 2 | 2 | 100.0% |
| swapped authors | 2 | 2 | 100.0% |
| wrong year | 3 | 2 | 66.7% |
| fake venue | 2 | 0 | 0.0% |
| invented | 2 | 2 | 100.0% |

| Class | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| Flagged (any problem) | 57.1% | 72.7% | 64.0% |
| NOT_FOUND | 50.0% | 100.0% | 66.7% |
| METADATA_MISMATCH | 50.0% | 55.6% | 52.6% |

Confusion matrix (rows: expected, columns: GhostCite):

| Expected | VERIFIED | METADATA_MISMATCH | NOT_FOUND | UNPARSEABLE | SKIPPED_BUDGET |
| --- | ---: | ---: | ---: | ---: | ---: |
| VERIFIED | 22 | 5 | 1 | 0 | 0 |
| METADATA_MISMATCH | 3 | 5 | 1 | 0 | 0 |
| NOT_FOUND | 0 | 0 | 2 | 0 | 0 |

Failures:

- `eco-akerlof-1970` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but year is 1978, not 1970. (Google Scholar lists this work with 46 versions; this may be a different version.)
- `eco-davis-1989` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but authors are FD DavisMIS quarterly, 1989•JSTOR, not Davis.
- `fab-venue-arun` (missed fabrication, fake venue): GhostCite said VERIFIED. Title and authors match a Google Scholar record (cited by 440).
- `fab-venue-fama` (missed fabrication, fake venue): GhostCite said VERIFIED. Title and authors match a Google Scholar record (cited by 37,962).
- `fab-year-huang` (missed fabrication, wrong year): GhostCite said VERIFIED. Title and authors match a Google Scholar record (cited by 67,433).
- `in-bhagwati-1993` (false alarm): GhostCite said NOT_FOUND. No Google Scholar record matches this title; the closest result was “India in transition: Freeing the economy” (88% similar).
- `in-bose-1924` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but authors are BoseZeitschrift für Physik, 1924•Springer, not Bose.
- `in-surappa-2003` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but authors are MK SurappaSadhana, 2003•Springer, not Surappa.
- `med-livak-2001` (false alarm): GhostCite said METADATA_MISMATCH. Title differs from the closest real paper: 'Analysis of relative gene expression data using real-time quantitative PCR and the 2− ΔΔCT method' (2001).

Detected, but with a different verdict than labelled:

- `fab-authors-livak`: expected METADATA_MISMATCH, got NOT_FOUND. No Google Scholar record matches this title; the closest result was “Analysis of relative gene expression data using real-time quantitative PCR and the 2− ΔΔCT method” (100% similar).

### Test split, BibTeX

39 references, 1 live searches in this run.

| Subset | Real | False alarms | False alarm rate | Fabricated | Detected | Detection rate | Unchecked |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All | 28 | 5 | 17.9% | 11 | 8 | 72.7% | 0 |
| Indian journals and books | 13 | 2 | 15.4% | 5 | 4 | 80.0% | 0 |

| Perturbation | Rows | Detected | Detection rate |
| --- | ---: | ---: | ---: |
| reworded title | 2 | 2 | 100.0% |
| swapped authors | 2 | 2 | 100.0% |
| wrong year | 3 | 2 | 66.7% |
| fake venue | 2 | 0 | 0.0% |
| invented | 2 | 2 | 100.0% |

| Class | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| Flagged (any problem) | 61.5% | 72.7% | 66.7% |
| NOT_FOUND | 66.7% | 100.0% | 80.0% |
| METADATA_MISMATCH | 50.0% | 55.6% | 52.6% |

Confusion matrix (rows: expected, columns: GhostCite):

| Expected | VERIFIED | METADATA_MISMATCH | NOT_FOUND | UNPARSEABLE | SKIPPED_BUDGET |
| --- | ---: | ---: | ---: | ---: | ---: |
| VERIFIED | 23 | 5 | 0 | 0 | 0 |
| METADATA_MISMATCH | 3 | 5 | 1 | 0 | 0 |
| NOT_FOUND | 0 | 0 | 2 | 0 | 0 |

Failures:

- `eco-akerlof-1970` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but year is 1978, not 1970. (Google Scholar lists this work with 46 versions; this may be a different version.)
- `eco-davis-1989` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but authors are FD DavisMIS quarterly, 1989•JSTOR, not Davis.
- `fab-venue-arun` (missed fabrication, fake venue): GhostCite said VERIFIED. Title and authors match a Google Scholar record (cited by 440).
- `fab-venue-fama` (missed fabrication, fake venue): GhostCite said VERIFIED. Title and authors match a Google Scholar record (cited by 37,962).
- `fab-year-huang` (missed fabrication, wrong year): GhostCite said VERIFIED. Title and authors match a Google Scholar record (cited by 67,433).
- `in-bose-1924` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but authors are BoseZeitschrift für Physik, 1924•Springer, not Bose.
- `in-surappa-2003` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but authors are MK SurappaSadhana, 2003•Springer, not Surappa.
- `med-livak-2001` (false alarm): GhostCite said METADATA_MISMATCH. Title differs from the closest real paper: 'Analysis of relative gene expression data using real-time quantitative PCR and the 2− ΔΔCT method' (2001).

Detected, but with a different verdict than labelled:

- `fab-authors-livak`: expected METADATA_MISMATCH, got NOT_FOUND. No Google Scholar record matches this title; the closest result was “Analysis of relative gene expression data using real-time quantitative PCR and the 2− ΔΔCT method” (100% similar).

### Tuning split, raw reference strings

28 references, 6 live searches in this run.

| Subset | Real | False alarms | False alarm rate | Fabricated | Detected | Detection rate | Unchecked |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All | 19 | 1 | 5.3% | 9 | 9 | 100.0% | 0 |
| Indian journals and books | 6 | 0 | 0.0% | 0 | 0 | n/a | 0 |

| Perturbation | Rows | Detected | Detection rate |
| --- | ---: | ---: | ---: |
| reworded title | 2 | 2 | 100.0% |
| swapped authors | 2 | 2 | 100.0% |
| wrong year | 1 | 1 | 100.0% |
| fake venue | 2 | 2 | 100.0% |
| invented | 2 | 2 | 100.0% |

| Class | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| Flagged (any problem) | 90.0% | 100.0% | 94.7% |
| NOT_FOUND | 50.0% | 100.0% | 66.7% |
| METADATA_MISMATCH | 83.3% | 71.4% | 76.9% |

Confusion matrix (rows: expected, columns: GhostCite):

| Expected | VERIFIED | METADATA_MISMATCH | NOT_FOUND | UNPARSEABLE | SKIPPED_BUDGET |
| --- | ---: | ---: | ---: | ---: | ---: |
| VERIFIED | 18 | 1 | 0 | 0 | 0 |
| METADATA_MISMATCH | 0 | 5 | 2 | 0 | 0 |
| NOT_FOUND | 0 | 0 | 2 | 0 | 0 |

Failures:

- `eco-markowitz-1952` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but year is 1955, not 1952. (Google Scholar lists this work with 54 versions; this may be a different version.)

Detected, but with a different verdict than labelled:

- `fab-reword-breiman`: expected METADATA_MISMATCH, got NOT_FOUND. No Google Scholar record matches this title; the closest result was “Pilot study on epidemiology and socioeconomic factors related to malaria in endemic communities of Bangladesh” (39% similar).
- `fab-reword-moher`: expected METADATA_MISMATCH, got NOT_FOUND. No Google Scholar record matches this title; the closest result was “Preferred reporting items for systematic reviews and meta-analyses: the PRISMA statement” (75% similar).

### Tuning split, BibTeX

28 references, 0 live searches in this run.

| Subset | Real | False alarms | False alarm rate | Fabricated | Detected | Detection rate | Unchecked |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All | 19 | 1 | 5.3% | 9 | 9 | 100.0% | 0 |
| Indian journals and books | 6 | 0 | 0.0% | 0 | 0 | n/a | 0 |

| Perturbation | Rows | Detected | Detection rate |
| --- | ---: | ---: | ---: |
| reworded title | 2 | 2 | 100.0% |
| swapped authors | 2 | 2 | 100.0% |
| wrong year | 1 | 1 | 100.0% |
| fake venue | 2 | 2 | 100.0% |
| invented | 2 | 2 | 100.0% |

| Class | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| Flagged (any problem) | 90.0% | 100.0% | 94.7% |
| NOT_FOUND | 50.0% | 100.0% | 66.7% |
| METADATA_MISMATCH | 83.3% | 71.4% | 76.9% |

Confusion matrix (rows: expected, columns: GhostCite):

| Expected | VERIFIED | METADATA_MISMATCH | NOT_FOUND | UNPARSEABLE | SKIPPED_BUDGET |
| --- | ---: | ---: | ---: | ---: | ---: |
| VERIFIED | 18 | 1 | 0 | 0 | 0 |
| METADATA_MISMATCH | 0 | 5 | 2 | 0 | 0 |
| NOT_FOUND | 0 | 0 | 2 | 0 | 0 |

Failures:

- `eco-markowitz-1952` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but year is 1955, not 1952. (Google Scholar lists this work with 54 versions; this may be a different version.)

Detected, but with a different verdict than labelled:

- `fab-reword-breiman`: expected METADATA_MISMATCH, got NOT_FOUND. No Google Scholar record matches this title; the closest result was “Pilot study on epidemiology and socioeconomic factors related to malaria in endemic communities of Bangladesh” (39% similar).
- `fab-reword-moher`: expected METADATA_MISMATCH, got NOT_FOUND. No Google Scholar record matches this title; the closest result was “Preferred reporting items for systematic reviews and meta-analyses: the PRISMA statement” (75% similar).
