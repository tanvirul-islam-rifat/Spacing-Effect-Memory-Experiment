# Notes on the submitted paper

The paper in this folder is the version submitted for PSY101 (7 September 2026), with student ID numbers redacted.
While building the reproducible analysis, the reported statistics were re-computed from the raw data.
Everything matched except the items below; **the numbers produced by this repository are the source of truth.**

| # | Item | In the submitted paper | Re-computed from the data |
|---|---|---|---|
| 1 | Table 2, Spaced column, score range 10–12 | 8 participants | **6** |
| 2 | Table 2, Spaced column, score range 13–15 | 7 participants | **9** |
| 3 | Hypothesis-test statistics | "significantly more words"; t and p not reported | t(34) = 6.46, two-sided p < .001 (see `results/analysis_summary.md`) |

All other reported values — means, SDs, medians, ranges, Shapiro–Wilk, Levene, mean difference, 95% CI, Cohen's d, the
54.4% relative improvement, and the "18 of 18" / "12 of 18" overlap statements — reproduce exactly.
The corrected frequency table is in `results/frequency_distribution.csv` and is checked by `tests/test_analysis.py`.
