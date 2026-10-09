# GhostCite evaluation results

Dataset: 67 validated references (0 dropped by validation). Split seed 20261009. Thresholds were tuned on the tuning split only.

**This is the held-out estimate**: the first and only run on the test split made before any change informed by it. Quote these test-split numbers.

### Test split, raw reference strings

39 references, 49 live searches in this run. Rates show counts and a 95% Wilson interval.

| Subset | False alarms on real references | Detection of fabricated references | Unchecked |
| --- | --- | --- | ---: |
| All | 6/28 = 21.4% [10.2, 39.5] | 8/11 = 72.7% [43.4, 90.3] | 0 |
| Indian journals and books | 3/13 = 23.1% [8.2, 50.3] | 4/5 = 80.0% [37.6, 96.4] | 0 |

Detection per perturbation type (counts only when fewer than 5 rows):

| Perturbation | Detected |
| --- | --- |
| reworded title | 2/2 |
| swapped authors | 2/2 |
| wrong year | 2/3 |
| fake venue | 0/2 |
| invented | 2/2 |

| Class | Precision | Recall | F1 |
| --- | --- | --- | ---: |
| Flagged (any problem) | 8/14 = 57.1% [32.6, 78.6] | 8/11 = 72.7% [43.4, 90.3] | 64.0% |
| NOT_FOUND | 2/4 = 50.0% [15.0, 85.0] | 2/2 = 100.0% [34.2, 100.0] | 66.7% |
| METADATA_MISMATCH | 5/10 = 50.0% [23.7, 76.3] | 5/9 = 55.6% [26.7, 81.1] | 52.6% |

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

39 references, 1 live searches in this run. Rates show counts and a 95% Wilson interval.

| Subset | False alarms on real references | Detection of fabricated references | Unchecked |
| --- | --- | --- | ---: |
| All | 5/28 = 17.9% [7.9, 35.6] | 8/11 = 72.7% [43.4, 90.3] | 0 |
| Indian journals and books | 2/13 = 15.4% [4.3, 42.2] | 4/5 = 80.0% [37.6, 96.4] | 0 |

Detection per perturbation type (counts only when fewer than 5 rows):

| Perturbation | Detected |
| --- | --- |
| reworded title | 2/2 |
| swapped authors | 2/2 |
| wrong year | 2/3 |
| fake venue | 0/2 |
| invented | 2/2 |

| Class | Precision | Recall | F1 |
| --- | --- | --- | ---: |
| Flagged (any problem) | 8/13 = 61.5% [35.5, 82.3] | 8/11 = 72.7% [43.4, 90.3] | 66.7% |
| NOT_FOUND | 2/3 = 66.7% [20.8, 93.9] | 2/2 = 100.0% [34.2, 100.0] | 80.0% |
| METADATA_MISMATCH | 5/10 = 50.0% [23.7, 76.3] | 5/9 = 55.6% [26.7, 81.1] | 52.6% |

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

28 references, 6 live searches in this run. Rates show counts and a 95% Wilson interval.

| Subset | False alarms on real references | Detection of fabricated references | Unchecked |
| --- | --- | --- | ---: |
| All | 1/19 = 5.3% [0.9, 24.6] | 9/9 = 100.0% [70.1, 100.0] | 0 |
| Indian journals and books | 0/6 = 0.0% [0.0, 39.0] | n/a | 0 |

Detection per perturbation type (counts only when fewer than 5 rows):

| Perturbation | Detected |
| --- | --- |
| reworded title | 2/2 |
| swapped authors | 2/2 |
| wrong year | 1/1 |
| fake venue | 2/2 |
| invented | 2/2 |

| Class | Precision | Recall | F1 |
| --- | --- | --- | ---: |
| Flagged (any problem) | 9/10 = 90.0% [59.6, 98.2] | 9/9 = 100.0% [70.1, 100.0] | 94.7% |
| NOT_FOUND | 2/4 = 50.0% [15.0, 85.0] | 2/2 = 100.0% [34.2, 100.0] | 66.7% |
| METADATA_MISMATCH | 5/6 = 83.3% [43.6, 97.0] | 5/7 = 71.4% [35.9, 91.8] | 76.9% |

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

28 references, 0 live searches in this run. Rates show counts and a 95% Wilson interval.

| Subset | False alarms on real references | Detection of fabricated references | Unchecked |
| --- | --- | --- | ---: |
| All | 1/19 = 5.3% [0.9, 24.6] | 9/9 = 100.0% [70.1, 100.0] | 0 |
| Indian journals and books | 0/6 = 0.0% [0.0, 39.0] | n/a | 0 |

Detection per perturbation type (counts only when fewer than 5 rows):

| Perturbation | Detected |
| --- | --- |
| reworded title | 2/2 |
| swapped authors | 2/2 |
| wrong year | 1/1 |
| fake venue | 2/2 |
| invented | 2/2 |

| Class | Precision | Recall | F1 |
| --- | --- | --- | ---: |
| Flagged (any problem) | 9/10 = 90.0% [59.6, 98.2] | 9/9 = 100.0% [70.1, 100.0] | 94.7% |
| NOT_FOUND | 2/4 = 50.0% [15.0, 85.0] | 2/2 = 100.0% [34.2, 100.0] | 66.7% |
| METADATA_MISMATCH | 5/6 = 83.3% [43.6, 97.0] | 5/7 = 71.4% [35.9, 91.8] | 76.9% |

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
