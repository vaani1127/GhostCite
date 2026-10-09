# Demo script (under 3 minutes, 1366×768)

Record at **1366×768** with the browser at 100% zoom and a terminal font of about 16 px.
The web UI and the report use the same 1080 px content width, so both fit without
horizontal scrolling.

## Before recording (one time, off camera)

1. `pip install .` in a fresh virtual environment. Put your key in `.env`.
2. Start the server: `ghostcite web`. Open <http://127.0.0.1:8000> and pick light or dark
   theme.
3. Do one dry run of the **live list below**.
   * If it has never been searched on this machine, it costs about 6 SerpApi searches
     (1 + 1 + 2 + 2). The dry run fills the local cache, so the recorded run costs **0
     searches**, which the report shows.
   * If you want the recording to show a real live search instead, run
     `ghostcite cache clear` first.
4. Close other tabs and notifications. Keep this script on a second screen.

## The four references to paste

```text
[1] A. Vaswani, N. Shazeer, N. Parmar et al., "Attention is all you need," Advances in Neural Information Processing Systems, 2017.
[2] S. Ren, K. He, R. Girshick, J. Sun, "Faster R-CNN: Towards real-time object detection with region proposal networks," NeurIPS, 2019.
[3] A. Vaswani et al., "Attention is all we need for sequence transduction," NeurIPS, 2017.
[4] R. K. Sharma and P. Mehta, "Quantum-inspired federated graph learning for monsoon crop yield prediction in Punjab," Indian Journal of Agricultural Informatics, vol. 14, no. 3, pp. 211-229, 2021.
```

Expected verdicts (checked against the recorded responses on this machine):

| # | Verdict | Reason shown |
| --- | --- | --- |
| 1 | **Verified** | Title, authors, year and venue match a Google Scholar record (cited by 274,507). |
| 2 | **Metadata mismatch**, with the versions note | Title matches, but year is 2015, not 2019. (Google Scholar lists this work with 20 versions; this may be a different version.) |
| 3 | **Metadata mismatch** (reworded title) | Title differs from the closest real paper: 'Attention is all you need' (2017). |
| 4 | **Not found** | No Google Scholar record was found for this title. |

Integrity score for this list: 50 / 100. The "cited by" and versions counts are live
Scholar data and may differ slightly on the day.

## Script

| Time | Screen | Say |
| --- | --- | --- |
| 0:00–0:12 | Web UI home page | "LLM-written papers cite papers that do not exist. GhostCite checks every reference against live Google Scholar data, through SerpApi." |
| 0:12–0:35 | Click **Try the sample**. Progress chips appear; the report opens. | "No key needed to try it: this is demo mode with recorded Scholar responses. Eleven references, real and fabricated, each with a verdict and a one-line reason." |
| 0:35–1:20 | Back to home. Paste the four references, keep **Live**, click **Check citations**. Open the report. | Walk the four rows: "One: verified. Two: the paper is real, but it is from 2015, not 2019, and Scholar lists 20 versions, so we say so. Three: someone reworded the title; GhostCite names the real paper. Four: this paper does not exist." |
| 1:20–1:40 | The report's summary card: score, verdict chips, run mode, credits used. Click **SARIF** and **HTML** under Download. | "One summary card: integrity score, counts per verdict, run mode, and the SerpApi credits used. This run was zero because the results were cached. Reports download as JSON, Markdown, self-contained HTML, or SARIF." |
| 1:40–2:00 | `docs/examples/ghostcite-workflow.yml` in the editor, or a code-scanning alert in a test repo | "SARIF powers the GitHub Action: every pull request that changes a .bib file gets code-scanning alerts on the exact line of a bad citation." |
| 2:00–2:25 | Terminal: `ghostcite check samples/sample.bib --demo --fail-on 1`, then `echo $LASTEXITCODE` (PowerShell) or `echo $?` (bash) | "The same engine in the CLI. With fail-on one, any bad reference makes the exit code one, so CI fails before a hallucinated citation is merged." |
| 2:25–2:50 | README evaluation table | "We evaluated on a frozen held-out set validated against Crossref: one false alarm in sixteen real references, eight of ten fabrications caught, including Indian journals. It is a small sample, so the confidence intervals are in the README, along with the limitations." |
| 2:50–2:58 | Repo URL | "GhostCite: open source, Apache-2.0. Thanks!" |

## Commands used

```bash
ghostcite web
ghostcite check samples/sample.bib --demo --fail-on 1
echo $LASTEXITCODE      # PowerShell; prints 1 (5 problems >= 1)
ghostcite check samples/sample.bib --demo -f sarif -o sample.sarif
```

A second run of the same live list hits the local cache and costs 0 credits. The
report's summary card shows "SerpApi credits used: 0".
