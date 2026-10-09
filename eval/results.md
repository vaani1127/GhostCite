# GhostCite evaluation results

Dataset: 67 validated references (0 dropped by validation). Split seed 20261009. Thresholds were tuned on the tuning split only.

**Post-fix rerun, not a held-out estimate.** Bugs found while reading the first test-split run were fixed before this run, so its test-split numbers are optimistic. Quote `eval/results_heldout_first_run.md` instead; docs/EVALUATION.md explains both.

### Test split, raw reference strings

39 references, 0 live searches in this run.

| Subset | Real | False alarms | False alarm rate | Fabricated | Detected | Detection rate | Unchecked |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All | 28 | 1 | 3.6% | 11 | 11 | 100.0% | 0 |
| Indian journals and books | 13 | 0 | 0.0% | 5 | 5 | 100.0% | 0 |

| Perturbation | Rows | Detected | Detection rate |
| --- | ---: | ---: | ---: |
| reworded title | 2 | 2 | 100.0% |
| swapped authors | 2 | 2 | 100.0% |
| wrong year | 3 | 3 | 100.0% |
| fake venue | 2 | 2 | 100.0% |
| invented | 2 | 2 | 100.0% |

| Class | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| Flagged (any problem) | 91.7% | 100.0% | 95.7% |
| NOT_FOUND | 100.0% | 100.0% | 100.0% |
| METADATA_MISMATCH | 90.0% | 100.0% | 94.7% |

Confusion matrix (rows: expected, columns: GhostCite):

| Expected | VERIFIED | METADATA_MISMATCH | NOT_FOUND | UNPARSEABLE | SKIPPED_BUDGET |
| --- | ---: | ---: | ---: | ---: | ---: |
| VERIFIED | 27 | 1 | 0 | 0 | 0 |
| METADATA_MISMATCH | 0 | 9 | 0 | 0 | 0 |
| NOT_FOUND | 0 | 0 | 2 | 0 | 0 |

Failures:

- `eco-akerlof-1970` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but year is 1978, not 1970. (Google Scholar lists this work with 46 versions; this may be a different version.)

### Test split, BibTeX

39 references, 0 live searches in this run.

| Subset | Real | False alarms | False alarm rate | Fabricated | Detected | Detection rate | Unchecked |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All | 28 | 1 | 3.6% | 11 | 11 | 100.0% | 0 |
| Indian journals and books | 13 | 0 | 0.0% | 5 | 5 | 100.0% | 0 |

| Perturbation | Rows | Detected | Detection rate |
| --- | ---: | ---: | ---: |
| reworded title | 2 | 2 | 100.0% |
| swapped authors | 2 | 2 | 100.0% |
| wrong year | 3 | 3 | 100.0% |
| fake venue | 2 | 2 | 100.0% |
| invented | 2 | 2 | 100.0% |

| Class | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| Flagged (any problem) | 91.7% | 100.0% | 95.7% |
| NOT_FOUND | 100.0% | 100.0% | 100.0% |
| METADATA_MISMATCH | 90.0% | 100.0% | 94.7% |

Confusion matrix (rows: expected, columns: GhostCite):

| Expected | VERIFIED | METADATA_MISMATCH | NOT_FOUND | UNPARSEABLE | SKIPPED_BUDGET |
| --- | ---: | ---: | ---: | ---: | ---: |
| VERIFIED | 27 | 1 | 0 | 0 | 0 |
| METADATA_MISMATCH | 0 | 9 | 0 | 0 | 0 |
| NOT_FOUND | 0 | 0 | 2 | 0 | 0 |

Failures:

- `eco-akerlof-1970` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but year is 1978, not 1970. (Google Scholar lists this work with 46 versions; this may be a different version.)

### Tuning split, raw reference strings

28 references, 0 live searches in this run.

| Subset | Real | False alarms | False alarm rate | Fabricated | Detected | Detection rate | Unchecked |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All | 19 | 2 | 10.5% | 9 | 9 | 100.0% | 0 |
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
| Flagged (any problem) | 81.8% | 100.0% | 90.0% |
| NOT_FOUND | 66.7% | 100.0% | 80.0% |
| METADATA_MISMATCH | 75.0% | 85.7% | 80.0% |

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

28 references, 0 live searches in this run.

| Subset | Real | False alarms | False alarm rate | Fabricated | Detected | Detection rate | Unchecked |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All | 19 | 2 | 10.5% | 9 | 9 | 100.0% | 0 |
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
| Flagged (any problem) | 81.8% | 100.0% | 90.0% |
| NOT_FOUND | 66.7% | 100.0% | 80.0% |
| METADATA_MISMATCH | 75.0% | 85.7% | 80.0% |

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
