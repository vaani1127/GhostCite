# GhostCite evaluation results

Dataset: 67 validated references (0 dropped by validation). Split seed 20261009. Thresholds were tuned on the tuning split only.

**Post-fix rerun, not a held-out estimate.** Bugs found while reading the first test-split run were fixed before this run, so its test-split numbers are optimistic. Quote `eval/results_heldout_first_run.md` instead; docs/EVALUATION.md explains both.

### Test split, raw reference strings

39 references, 0 live searches in this run. Rates show counts and a 95% Wilson interval.

| Subset | False alarms on real references | Detection of fabricated references | Unchecked |
| --- | --- | --- | ---: |
| All | 1/28 = 3.6% [0.6, 17.7] | 11/11 = 100.0% [74.1, 100.0] | 0 |
| Indian journals and books | 0/13 = 0.0% [0.0, 22.8] | 5/5 = 100.0% [56.6, 100.0] | 0 |

Detection per perturbation type (counts only when fewer than 5 rows):

| Perturbation | Detected |
| --- | --- |
| reworded title | 2/2 |
| swapped authors | 2/2 |
| wrong year | 3/3 |
| fake venue | 2/2 |
| invented | 2/2 |

| Class | Precision | Recall | F1 |
| --- | --- | --- | ---: |
| Flagged (any problem) | 11/12 = 91.7% [64.6, 98.5] | 11/11 = 100.0% [74.1, 100.0] | 95.7% |
| NOT_FOUND | 2/2 = 100.0% [34.2, 100.0] | 2/2 = 100.0% [34.2, 100.0] | 100.0% |
| METADATA_MISMATCH | 9/10 = 90.0% [59.6, 98.2] | 9/9 = 100.0% [70.1, 100.0] | 94.7% |

Confusion matrix (rows: expected, columns: GhostCite):

| Expected | VERIFIED | METADATA_MISMATCH | NOT_FOUND | UNPARSEABLE | SKIPPED_BUDGET |
| --- | ---: | ---: | ---: | ---: | ---: |
| VERIFIED | 27 | 1 | 0 | 0 | 0 |
| METADATA_MISMATCH | 0 | 9 | 0 | 0 | 0 |
| NOT_FOUND | 0 | 0 | 2 | 0 | 0 |

Failures:

- `eco-akerlof-1970` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but year is 1978, not 1970. (Google Scholar lists this work with 46 versions; this may be a different version.)

### Test split, BibTeX

39 references, 0 live searches in this run. Rates show counts and a 95% Wilson interval.

| Subset | False alarms on real references | Detection of fabricated references | Unchecked |
| --- | --- | --- | ---: |
| All | 1/28 = 3.6% [0.6, 17.7] | 11/11 = 100.0% [74.1, 100.0] | 0 |
| Indian journals and books | 0/13 = 0.0% [0.0, 22.8] | 5/5 = 100.0% [56.6, 100.0] | 0 |

Detection per perturbation type (counts only when fewer than 5 rows):

| Perturbation | Detected |
| --- | --- |
| reworded title | 2/2 |
| swapped authors | 2/2 |
| wrong year | 3/3 |
| fake venue | 2/2 |
| invented | 2/2 |

| Class | Precision | Recall | F1 |
| --- | --- | --- | ---: |
| Flagged (any problem) | 11/12 = 91.7% [64.6, 98.5] | 11/11 = 100.0% [74.1, 100.0] | 95.7% |
| NOT_FOUND | 2/2 = 100.0% [34.2, 100.0] | 2/2 = 100.0% [34.2, 100.0] | 100.0% |
| METADATA_MISMATCH | 9/10 = 90.0% [59.6, 98.2] | 9/9 = 100.0% [70.1, 100.0] | 94.7% |

Confusion matrix (rows: expected, columns: GhostCite):

| Expected | VERIFIED | METADATA_MISMATCH | NOT_FOUND | UNPARSEABLE | SKIPPED_BUDGET |
| --- | ---: | ---: | ---: | ---: | ---: |
| VERIFIED | 27 | 1 | 0 | 0 | 0 |
| METADATA_MISMATCH | 0 | 9 | 0 | 0 | 0 |
| NOT_FOUND | 0 | 0 | 2 | 0 | 0 |

Failures:

- `eco-akerlof-1970` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but year is 1978, not 1970. (Google Scholar lists this work with 46 versions; this may be a different version.)

### Tuning split, raw reference strings

28 references, 0 live searches in this run. Rates show counts and a 95% Wilson interval.

| Subset | False alarms on real references | Detection of fabricated references | Unchecked |
| --- | --- | --- | ---: |
| All | 2/19 = 10.5% [2.9, 31.4] | 9/9 = 100.0% [70.1, 100.0] | 0 |
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
| Flagged (any problem) | 9/11 = 81.8% [52.3, 94.9] | 9/9 = 100.0% [70.1, 100.0] | 90.0% |
| NOT_FOUND | 2/3 = 66.7% [20.8, 93.9] | 2/2 = 100.0% [34.2, 100.0] | 80.0% |
| METADATA_MISMATCH | 6/8 = 75.0% [40.9, 92.9] | 6/7 = 85.7% [48.7, 97.4] | 80.0% |

Confusion matrix (rows: expected, columns: GhostCite):

| Expected | VERIFIED | METADATA_MISMATCH | NOT_FOUND | UNPARSEABLE | SKIPPED_BUDGET |
| --- | ---: | ---: | ---: | ---: | ---: |
| VERIFIED | 17 | 2 | 0 | 0 | 0 |
| METADATA_MISMATCH | 0 | 6 | 1 | 0 | 0 |
| NOT_FOUND | 0 | 0 | 2 | 0 | 0 |

Failures:

- `eco-jensen-1976` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but year is 2019, not 1976; venue is Corporate governance, not Journal of Financial Economics. (Google Scholar lists this work with 31 versions; this may be a different version.)
- `eco-markowitz-1952` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but year is 1955, not 1952. (Google Scholar lists this work with 54 versions; this may be a different version.)

Detected, but with a different verdict than labelled:

- `fab-reword-breiman`: expected METADATA_MISMATCH, got NOT_FOUND. No Google Scholar record matches this title; the closest result was “Pilot study on epidemiology and socioeconomic factors related to malaria in endemic communities of Bangladesh” (39% similar).

### Tuning split, BibTeX

28 references, 0 live searches in this run. Rates show counts and a 95% Wilson interval.

| Subset | False alarms on real references | Detection of fabricated references | Unchecked |
| --- | --- | --- | ---: |
| All | 2/19 = 10.5% [2.9, 31.4] | 9/9 = 100.0% [70.1, 100.0] | 0 |
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
| Flagged (any problem) | 9/11 = 81.8% [52.3, 94.9] | 9/9 = 100.0% [70.1, 100.0] | 90.0% |
| NOT_FOUND | 2/3 = 66.7% [20.8, 93.9] | 2/2 = 100.0% [34.2, 100.0] | 80.0% |
| METADATA_MISMATCH | 6/8 = 75.0% [40.9, 92.9] | 6/7 = 85.7% [48.7, 97.4] | 80.0% |

Confusion matrix (rows: expected, columns: GhostCite):

| Expected | VERIFIED | METADATA_MISMATCH | NOT_FOUND | UNPARSEABLE | SKIPPED_BUDGET |
| --- | ---: | ---: | ---: | ---: | ---: |
| VERIFIED | 17 | 2 | 0 | 0 | 0 |
| METADATA_MISMATCH | 0 | 6 | 1 | 0 | 0 |
| NOT_FOUND | 0 | 0 | 2 | 0 | 0 |

Failures:

- `eco-jensen-1976` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but year is 2019, not 1976; venue is Corporate governance, not Journal of Financial Economics. (Google Scholar lists this work with 31 versions; this may be a different version.)
- `eco-markowitz-1952` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but year is 1955, not 1952. (Google Scholar lists this work with 54 versions; this may be a different version.)

Detected, but with a different verdict than labelled:

- `fab-reword-breiman`: expected METADATA_MISMATCH, got NOT_FOUND. No Google Scholar record matches this title; the closest result was “Pilot study on epidemiology and socioeconomic factors related to malaria in endemic communities of Bangladesh” (39% similar).
