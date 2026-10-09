# GhostCite evaluation results

Dataset: 26 validated references (0 dropped by validation). SHA-256 `sha256:e7e752544795eeabbd24b2a66f94ccbef04660b4bc341a6d6d22a83cf8888604`.

**Frozen held-out set v2 (headline result).** The dataset shares no paper with v1, was frozen (SHA-256 in docs/EVALUATION.md) before any search, and was run exactly once with the code frozen. No code was changed in response to these results.

### Held-out v2, raw reference strings

26 references, 29 live searches in this run. Rates show counts and a 95% Wilson interval.

| Subset | False alarms on real references | Detection of fabricated references | Unchecked |
| --- | --- | --- | ---: |
| All | 1/16 = 6.2% [1.1, 28.3] | 8/10 = 80.0% [49.0, 94.3] | 0 |
| Indian journals and books | 0/7 = 0.0% [0.0, 35.4] | 4/5 = 80.0% [37.6, 96.4] | 0 |

Detection per perturbation type (counts only when fewer than 5 rows):

| Perturbation | Detected |
| --- | --- |
| reworded title | 2/2 |
| swapped authors | 2/2 |
| wrong year | 2/2 |
| fake venue | 0/2 |
| invented | 2/2 |

| Class | Precision | Recall | F1 |
| --- | --- | --- | ---: |
| Flagged (any problem) | 8/9 = 88.9% [56.5, 98.0] | 8/10 = 80.0% [49.0, 94.3] | 84.2% |
| NOT_FOUND | 2/2 = 100.0% [34.2, 100.0] | 2/2 = 100.0% [34.2, 100.0] | 100.0% |
| METADATA_MISMATCH | 6/7 = 85.7% [48.7, 97.4] | 6/8 = 75.0% [40.9, 92.9] | 80.0% |

Confusion matrix (rows: expected, columns: GhostCite):

| Expected | VERIFIED | METADATA_MISMATCH | NOT_FOUND | UNPARSEABLE | SKIPPED_BUDGET |
| --- | ---: | ---: | ---: | ---: | ---: |
| VERIFIED | 15 | 1 | 0 | 0 | 0 |
| METADATA_MISMATCH | 2 | 6 | 0 | 0 | 0 |
| NOT_FOUND | 0 | 0 | 2 | 0 | 0 |

Failures:

- `fab-venue-gadagkar` (missed fabrication, fake venue): GhostCite said VERIFIED. Title, authors and year match a Google Scholar record (cited by 59).
- `fab-venue-myers` (missed fabrication, fake venue): GhostCite said VERIFIED. Title, authors and year match a Google Scholar record (cited by 45,206).
- `soc-granovetter-1973` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but year is 1977, not 1973; venue is Social networks, not American Journal of Sociology. (Google Scholar lists this work with 94 versions; this may be a different version.)

### Held-out v2, BibTeX

26 references, 0 live searches in this run. Rates show counts and a 95% Wilson interval.

| Subset | False alarms on real references | Detection of fabricated references | Unchecked |
| --- | --- | --- | ---: |
| All | 1/16 = 6.2% [1.1, 28.3] | 8/10 = 80.0% [49.0, 94.3] | 0 |
| Indian journals and books | 0/7 = 0.0% [0.0, 35.4] | 4/5 = 80.0% [37.6, 96.4] | 0 |

Detection per perturbation type (counts only when fewer than 5 rows):

| Perturbation | Detected |
| --- | --- |
| reworded title | 2/2 |
| swapped authors | 2/2 |
| wrong year | 2/2 |
| fake venue | 0/2 |
| invented | 2/2 |

| Class | Precision | Recall | F1 |
| --- | --- | --- | ---: |
| Flagged (any problem) | 8/9 = 88.9% [56.5, 98.0] | 8/10 = 80.0% [49.0, 94.3] | 84.2% |
| NOT_FOUND | 2/2 = 100.0% [34.2, 100.0] | 2/2 = 100.0% [34.2, 100.0] | 100.0% |
| METADATA_MISMATCH | 6/7 = 85.7% [48.7, 97.4] | 6/8 = 75.0% [40.9, 92.9] | 80.0% |

Confusion matrix (rows: expected, columns: GhostCite):

| Expected | VERIFIED | METADATA_MISMATCH | NOT_FOUND | UNPARSEABLE | SKIPPED_BUDGET |
| --- | ---: | ---: | ---: | ---: | ---: |
| VERIFIED | 15 | 1 | 0 | 0 | 0 |
| METADATA_MISMATCH | 2 | 6 | 0 | 0 | 0 |
| NOT_FOUND | 0 | 0 | 2 | 0 | 0 |

Failures:

- `fab-venue-gadagkar` (missed fabrication, fake venue): GhostCite said VERIFIED. Title, authors and year match a Google Scholar record (cited by 59).
- `fab-venue-myers` (missed fabrication, fake venue): GhostCite said VERIFIED. Title, authors and year match a Google Scholar record (cited by 45,206).
- `soc-granovetter-1973` (false alarm): GhostCite said METADATA_MISMATCH. Title matches, but year is 1977, not 1973; venue is Social networks, not American Journal of Sociology. (Google Scholar lists this work with 94 versions; this may be a different version.)
