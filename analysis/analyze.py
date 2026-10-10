#!/usr/bin/env python3
"""Reproducible analysis for the spaced-vs-massed practice experiment.

Reproduces every statistic reported in the paper from ``data/spacing_effect_data.csv``
and adds robustness checks (non-parametric, permutation, bootstrap, covariate-adjusted).

Usage:
    python analysis/analyze.py                       # writes results/ and figures/
    python analysis/analyze.py --data other.csv --out-results r/ --out-figures f/
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.formula.api as smf  # noqa: E402
from scipy import stats  # noqa: E402

SEED = 42
N_PERMUTATIONS = 20_000
N_BOOTSTRAP = 10_000
GROUPS = ("Massed", "Spaced")
COLORS = {"Massed": "#6B6B85", "Spaced": "#E5833B"}
SCORE_BINS = [(4, 6), (7, 9), (10, 12), (13, 15), (16, 18)]  # score ranges used in the paper (Table 2)
REQUIRED = ["participant_id", "condition", "researcher", "age", "gender", "year_of_study", "words_recalled"]

plt.rcParams.update(
    {
        "font.family": "DejaVu Serif",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.alpha": 0.25,
        "figure.dpi": 130,
        "savefig.bbox": "tight",
    }
)


# --------------------------------------------------------------------------- data
def load_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    if df[REQUIRED].isna().any().any():
        raise ValueError("dataset contains missing values")
    if set(df["condition"]) != set(GROUPS):
        raise ValueError(f"condition must be one of {GROUPS}")
    if not df["words_recalled"].between(0, 20).all():
        raise ValueError("words_recalled must be within 0-20")
    if df["participant_id"].duplicated().any():
        raise ValueError("duplicate participant IDs")
    df = df.copy()
    df["spaced"] = (df["condition"] == "Spaced").astype(int)
    return df


def split(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    return (
        df.loc[df.condition == "Massed", "words_recalled"].to_numpy(float),
        df.loc[df.condition == "Spaced", "words_recalled"].to_numpy(float),
    )


def fmt_p(p: float) -> str:
    return "< .001" if p < 0.001 else f"= {p:.3f}".replace("0.", ".", 1)


# ------------------------------------------------------------------ descriptives
def descriptives(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for g in GROUPS:
        x = df.loc[df.condition == g, "words_recalled"].to_numpy(float)
        n, m, sd = len(x), x.mean(), x.std(ddof=1)
        se = sd / np.sqrt(n)
        tcrit = stats.t.ppf(0.975, n - 1)
        rows.append(
            dict(condition=g, n=n, mean=m, sd=sd, se=se, median=np.median(x), min=x.min(), max=x.max(),
                 ci95_low=m - tcrit * se, ci95_high=m + tcrit * se)
        )
    return pd.DataFrame(rows)


def frequency_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for lo, hi in SCORE_BINS:
        row = {"score_range": f"{lo}-{hi}"}
        for g in GROUPS:
            s = df.loc[df.condition == g, "words_recalled"]
            row[g] = int(s.between(lo, hi).sum())
        rows.append(row)
    table = pd.DataFrame(rows)
    assert table[list(GROUPS)].sum().tolist() == [int((df.condition == g).sum()) for g in GROUPS]
    return table


# ------------------------------------------------------------------ inference
def assumption_checks(massed: np.ndarray, spaced: np.ndarray) -> dict:
    out = {}
    for name, x in (("massed", massed), ("spaced", spaced)):
        w, p = stats.shapiro(x)
        out[f"shapiro_{name}"] = {"W": w, "p": p}
    f, p = stats.levene(massed, spaced)  # Brown-Forsythe (median-centred), scipy default
    out["levene"] = {"F": f, "p": p}
    out["sd_ratio"] = max(massed.std(ddof=1), spaced.std(ddof=1)) / min(massed.std(ddof=1), spaced.std(ddof=1))
    return out


def primary_tests(massed: np.ndarray, spaced: np.ndarray, rng: np.random.Generator) -> dict:
    n1, n2 = len(massed), len(spaced)
    dfree = n1 + n2 - 2
    diff = spaced.mean() - massed.mean()
    sp = np.sqrt(((n1 - 1) * massed.var(ddof=1) + (n2 - 1) * spaced.var(ddof=1)) / dfree)
    se = sp * np.sqrt(1 / n1 + 1 / n2)
    tcrit = stats.t.ppf(0.975, dfree)

    student = stats.ttest_ind(spaced, massed)
    student_one = stats.ttest_ind(spaced, massed, alternative="greater")
    welch = stats.ttest_ind(spaced, massed, equal_var=False)

    d = diff / sp
    j = 1 - 3 / (4 * dfree - 1)
    se_d = np.sqrt((n1 + n2) / (n1 * n2) + d**2 / (2 * (n1 + n2)))

    u = stats.mannwhitneyu(spaced, massed, alternative="two-sided")
    u_stat = float(stats.mannwhitneyu(spaced, massed, alternative="greater").statistic)

    # permutation test on the difference in means (one-sided, H_A: spaced > massed)
    pooled = np.concatenate([massed, spaced])
    obs = diff
    count = 0
    for _ in range(N_PERMUTATIONS):
        perm = rng.permutation(pooled)
        if perm[n1:].mean() - perm[:n1].mean() >= obs - 1e-12:
            count += 1
    p_perm = (count + 1) / (N_PERMUTATIONS + 1)

    boots = np.array(
        [rng.choice(spaced, n2).mean() - rng.choice(massed, n1).mean() for _ in range(N_BOOTSTRAP)]
    )

    return {
        "mean_difference": diff,
        "relative_improvement_pct": 100 * diff / massed.mean(),
        "df": dfree,
        "pooled_sd": sp,
        "ci95_difference": [diff - tcrit * se, diff + tcrit * se],
        "student_t": {"t": float(student.statistic), "p_two_sided": float(student.pvalue),
                      "p_one_sided": float(student_one.pvalue)},
        "welch_t": {"t": float(welch.statistic), "df": float(welch.df), "p_two_sided": float(welch.pvalue)},
        "cohens_d": d,
        "cohens_d_ci95_approx": [d - 1.96 * se_d, d + 1.96 * se_d],
        "hedges_g": d * j,
        "mann_whitney": {"U": u_stat, "p_two_sided": float(u.pvalue),
                         "prob_superiority": u_stat / (n1 * n2)},
        "permutation_p_one_sided": p_perm,
        "bootstrap_ci95_difference": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
        "_bootstrap_samples": boots,
    }


def robustness_models(df: pd.DataFrame) -> pd.DataFrame:
    specs = {
        "M1: condition only": "words_recalled ~ spaced",
        "M2: + gender": "words_recalled ~ spaced + C(gender)",
        "M3: + gender, year, age": "words_recalled ~ spaced + C(gender) + C(year_of_study) + age",
        "M4: + researcher": "words_recalled ~ spaced + C(gender) + C(year_of_study) + age + C(researcher)",
    }
    rows = []
    for name, formula in specs.items():
        fit = smf.ols(formula, df).fit(cov_type="HC3")
        lo, hi = fit.conf_int().loc["spaced"]
        rows.append(dict(model=name, spaced_effect=fit.params["spaced"], ci95_low=lo, ci95_high=hi,
                         p_value=fit.pvalues["spaced"], n=int(fit.nobs), r_squared=fit.rsquared))
    return pd.DataFrame(rows)


def balance_checks(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    g = pd.crosstab(df.gender, df.condition).reindex(columns=list(GROUPS))
    odds, p = stats.fisher_exact(g.loc[["Female", "Male"]].to_numpy())
    rows.append(dict(variable="gender", test="Fisher exact", statistic=odds, p_value=p,
                     detail=f"Female {g.loc['Female','Massed']}/{g.loc['Female','Spaced']}, "
                            f"Male {g.loc['Male','Massed']}/{g.loc['Male','Spaced']} (massed/spaced)"))
    y = pd.crosstab(df.year_of_study, df.condition)
    chi2, p, _, _ = stats.chi2_contingency(y)
    rows.append(dict(variable="year_of_study", test="chi-square", statistic=chi2, p_value=p,
                     detail="; ".join(f"year {k}: {r['Massed']}/{r['Spaced']}" for k, r in y.iterrows())))
    a_m, a_s = (df.loc[df.condition == c, "age"] for c in GROUPS)
    t = stats.ttest_ind(a_s, a_m, equal_var=False)
    rows.append(dict(variable="age", test="Welch t", statistic=t.statistic, p_value=t.pvalue,
                     detail=f"mean age massed {a_m.mean():.2f}, spaced {a_s.mean():.2f}"))
    r = pd.crosstab(df.researcher, df.condition)
    rows.append(dict(variable="researcher", test="allocation counts", statistic=np.nan, p_value=np.nan,
                     detail="; ".join(f"{k}: {x['Massed']}/{x['Spaced']}" for k, x in r.iterrows())))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------- figures
def _style_axis(ax, ylabel=None):
    ax.set_ylabel(ylabel or "")
    ax.tick_params(axis="x", length=0)


def fig_design(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 3.4))
    study, gap, ret, rec = "#4C72B0", "#D9D9D9", "#EFEFEF", "#2E7D32"
    rows = {
        "Massed": [("Study\n2 min", 12, COLORS["Massed"]), ("Retention filler task\n10–15 min", 30, ret),
                   ("Free recall\n2 min", 9, rec)],
        "Spaced": [("S1\n40 s", 4, COLORS["Spaced"]), ("filler\n1 min", 3, gap), ("S2\n40 s", 4, COLORS["Spaced"]),
                   ("filler\n1 min", 3, gap), ("S3\n40 s", 4, COLORS["Spaced"]),
                   ("Retention filler task\n10–15 min", 30, ret), ("Free recall\n2 min", 9, rec)],
    }
    for y, (name, segs) in zip((1, 0), rows.items()):
        x = 0
        for label, w, c in segs:
            ax.barh(y, w, left=x, height=0.62, color=c, edgecolor="white", lw=1.5)
            dark = c in (COLORS["Massed"], COLORS["Spaced"], rec, study)
            ax.text(x + w / 2, y, label, ha="center", va="center", fontsize=8.5,
                    color="white" if dark else "#333333", fontweight="bold" if dark else "normal")
            x += w
        ax.text(-1, y, name, ha="right", va="center", fontsize=11, fontweight="bold", color=COLORS[name])
    ax.set_xlim(-9, 56)
    ax.set_ylim(-0.6, 1.6)
    ax.axis("off")
    ax.set_title("Experimental design — equal total study exposure (2 min), different schedule\n"
                 "(schematic, not drawn to scale)", fontsize=11)
    fig.savefig(path)
    plt.close(fig)


def fig_means(desc: pd.DataFrame, tests: dict, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.2, 4.4))
    for i, g in enumerate(GROUPS):
        r = desc.set_index("condition").loc[g]
        ax.bar(i, r["mean"], color=COLORS[g], edgecolor="black", lw=0.8, width=0.6)
        ax.errorbar(i, r["mean"], yerr=r["se"], color="black", capsize=6, lw=1.4)
        ax.text(i, r["mean"] + r["se"] + 0.35, f"{r['mean']:.2f}", ha="center", fontsize=10)
    ax.set_xticks([0, 1], GROUPS)
    ax.set_ylim(0, 20)
    ax.set_ylabel("Mean words recalled (out of 20)")
    t = tests["student_t"]
    ax.set_title(f"t({tests['df']}) = {t['t']:.2f}, p {fmt_p(t['p_two_sided'])}, d = {tests['cohens_d']:.2f}",
                 fontsize=10)
    ax.text(0.5, -0.17, "Error bars: ±1 SE of the mean", transform=ax.transAxes, ha="center", fontsize=8,
            style="italic")
    fig.savefig(path)
    plt.close(fig)


def fig_individual(df: pd.DataFrame, desc: pd.DataFrame, path: Path) -> None:
    rng = np.random.default_rng(SEED)
    fig, ax = plt.subplots(figsize=(5.8, 4.8))
    for i, g in enumerate(GROUPS):
        y = df.loc[df.condition == g, "words_recalled"].to_numpy()
        x = i + rng.uniform(-0.17, 0.17, len(y))
        ax.scatter(x, y, s=48, color=COLORS[g], edgecolor="black", lw=0.7, alpha=0.9, zorder=3)
        m = desc.set_index("condition").loc[g, "mean"]
        ax.hlines(m, i - 0.32, i + 0.32, color="black", lw=2.2, zorder=4)
    ax.set_xticks([0, 1], GROUPS)
    ax.set_ylim(2, 19)
    ax.set_xlim(-0.6, 1.6)
    ax.set_ylabel("Words recalled (out of 20)")
    ax.set_title("Individual recall scores (one dot = one participant)", fontsize=10)
    ax.text(0.5, -0.12, "Horizontal bars: condition means", transform=ax.transAxes, ha="center", fontsize=8,
            style="italic")
    fig.savefig(path)
    plt.close(fig)


def fig_distribution(freq: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    x = np.arange(len(freq))
    w = 0.38
    for k, g in enumerate(GROUPS):
        bars = ax.bar(x + (k - 0.5) * w, freq[g], w, color=COLORS[g], edgecolor="black", lw=0.7, label=g)
        for b in bars:
            if b.get_height():
                ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.15, int(b.get_height()), ha="center",
                        fontsize=9)
    ax.set_xticks(x, freq["score_range"])
    ax.set_xlabel("Words recalled (score range)")
    ax.set_ylabel("Participants (n)")
    ax.set_title("Frequency distribution of recall scores", fontsize=10)
    ax.legend(frameon=False)
    fig.savefig(path)
    plt.close(fig)


def fig_effect(tests: dict, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    boots = tests["_bootstrap_samples"]
    ax.hist(boots, bins=45, color="#E5833B", edgecolor="white", alpha=0.9)
    lo, hi = tests["bootstrap_ci95_difference"]
    ax.axvline(tests["mean_difference"], color="black", lw=2)
    ax.axvspan(lo, hi, color="grey", alpha=0.18)
    ax.axvline(0, color="red", ls="--", lw=1)
    ax.set_xlabel("Spaced − massed mean difference (words)")
    ax.set_ylabel("Bootstrap resamples")
    ax.set_title(f"Mean difference = {tests['mean_difference']:.2f} words; "
                 f"bootstrap 95% CI [{lo:.2f}, {hi:.2f}]", fontsize=10)
    ax.text(0.02, 0.9, "red dashed: no effect", transform=ax.transAxes, color="red", fontsize=8)
    fig.savefig(path)
    plt.close(fig)


def fig_robustness(rob: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    y = np.arange(len(rob))[::-1]
    ax.errorbar(rob.spaced_effect, y, xerr=[rob.spaced_effect - rob.ci95_low, rob.ci95_high - rob.spaced_effect],
                fmt="o", color="#E5833B", ecolor="black", capsize=4, ms=7, mec="black")
    ax.axvline(0, color="red", ls="--", lw=1)
    ax.set_yticks(y, rob.model)
    ax.set_xlabel("Estimated spaced-practice advantage (words), 95% CI (HC3 robust SE)")
    ax.set_title("The effect is stable under covariate adjustment", fontsize=10)
    ax.set_xlim(0, 7)
    fig.savefig(path)
    plt.close(fig)


def fig_assumptions(massed: np.ndarray, spaced: np.ndarray, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.8), sharey=False)
    for ax, g, x in zip(axes, GROUPS, (massed, spaced)):
        (osm, osr), (slope, intercept, r) = stats.probplot(x, dist="norm")
        ax.scatter(osm, osr, color=COLORS[g], edgecolor="black", lw=0.6, s=40)
        ax.plot(osm, slope * np.asarray(osm) + intercept, color="black", lw=1)
        w, p = stats.shapiro(x)
        ax.set_title(f"{g}: Shapiro–Wilk W = {w:.2f}, p {fmt_p(p)}", fontsize=9.5)
        ax.set_xlabel("Theoretical quantiles")
    axes[0].set_ylabel("Observed recall scores")
    fig.suptitle("Normality check (Q–Q plots)", fontsize=11)
    fig.savefig(path)
    plt.close(fig)


# ---------------------------------------------------------------------- report
def write_summary(path: Path, desc, assume, tests, rob, bal, freq, n) -> None:
    d = desc.set_index("condition")
    st, wt, mw = tests["student_t"], tests["welch_t"], tests["mann_whitney"]
    lines = [
        "# Analysis summary (auto-generated by `analysis/analyze.py`)",
        "",
        f"**Sample:** N = {n} (18 per condition). **Outcome:** words recalled out of 20.",
        "",
        "## Descriptive statistics",
        "",
        "| Condition | n | M | SD | SE | Mdn | Min | Max | 95% CI of mean |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for g in GROUPS:
        r = d.loc[g]
        lines.append(f"| {g} | {int(r.n)} | {r['mean']:.2f} | {r.sd:.2f} | {r.se:.2f} | {r['median']:.2f} | "
                     f"{int(r['min'])} | {int(r['max'])} | [{r.ci95_low:.2f}, {r.ci95_high:.2f}] |")
    lines += [
        "",
        "## Assumption checks",
        "",
        f"- Shapiro–Wilk, massed: W = {assume['shapiro_massed']['W']:.2f}, p {fmt_p(assume['shapiro_massed']['p'])}",
        f"- Shapiro–Wilk, spaced: W = {assume['shapiro_spaced']['W']:.2f}, p {fmt_p(assume['shapiro_spaced']['p'])}",
        f"- Levene (median-centred): F = {assume['levene']['F']:.2f}, p {fmt_p(assume['levene']['p'])}; "
        f"SD ratio = {assume['sd_ratio']:.2f}",
        "",
        "## Hypothesis test",
        "",
        f"- Independent-samples t-test: t({tests['df']}) = {st['t']:.2f}, two-sided p {fmt_p(st['p_two_sided'])} "
        f"(one-sided, H_A: spaced > massed: p {fmt_p(st['p_one_sided'])})",
        f"- Welch t-test: t({wt['df']:.1f}) = {wt['t']:.2f}, p {fmt_p(wt['p_two_sided'])}",
        f"- Mean difference = {tests['mean_difference']:.2f} words "
        f"(95% CI [{tests['ci95_difference'][0]:.2f}, {tests['ci95_difference'][1]:.2f}]); "
        f"{tests['relative_improvement_pct']:.1f}% relative improvement over massed",
        f"- Cohen's d = {tests['cohens_d']:.2f} (approx. 95% CI [{tests['cohens_d_ci95_approx'][0]:.2f}, "
        f"{tests['cohens_d_ci95_approx'][1]:.2f}]); Hedges' g = {tests['hedges_g']:.2f}",
        "",
        "## Robustness",
        "",
        f"- Mann–Whitney U = {mw['U']:.0f}, p {fmt_p(mw['p_two_sided'])}; probability of superiority = "
        f"{mw['prob_superiority']:.2f}",
        f"- Permutation test ({N_PERMUTATIONS:,} resamples, one-sided): p {fmt_p(tests['permutation_p_one_sided'])}",
        f"- Bootstrap 95% CI for the difference ({N_BOOTSTRAP:,} resamples): "
        f"[{tests['bootstrap_ci95_difference'][0]:.2f}, {tests['bootstrap_ci95_difference'][1]:.2f}]",
        "",
        "| Model | Spaced effect | 95% CI | p | n |",
        "|---|---|---|---|---|",
    ]
    for _, r in rob.iterrows():
        lines.append(f"| {r.model} | {r.spaced_effect:.2f} | [{r.ci95_low:.2f}, {r.ci95_high:.2f}] | "
                     f"{fmt_p(r.p_value)} | {r.n} |")
    lines += ["", "## Group balance", "", "| Variable | Test | Statistic | p | Detail |", "|---|---|---|---|---|"]
    for _, r in bal.iterrows():
        stat = "" if pd.isna(r.statistic) else f"{r.statistic:.2f}"
        pv = "" if pd.isna(r.p_value) else fmt_p(r.p_value)
        lines.append(f"| {r.variable} | {r.test} | {stat} | {pv} | {r.detail} |")
    lines += ["", "## Frequency distribution (n per score range)", "", "| Score range | Massed | Spaced |", "|---|---|---|"]
    for _, r in freq.iterrows():
        lines.append(f"| {r.score_range} | {r.Massed} | {r.Spaced} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------------ main
def run(data_path: Path, out_results: Path, out_figures: Path) -> dict:
    out_results.mkdir(parents=True, exist_ok=True)
    out_figures.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    df = load_data(data_path)
    massed, spaced = split(df)
    desc = descriptives(df)
    freq = frequency_table(df)
    assume = assumption_checks(massed, spaced)
    tests = primary_tests(massed, spaced, rng)
    rob = robustness_models(df)
    bal = balance_checks(df)

    desc.round(4).to_csv(out_results / "descriptive_statistics.csv", index=False)
    freq.to_csv(out_results / "frequency_distribution.csv", index=False)
    rob.round(4).to_csv(out_results / "robustness_models.csv", index=False)
    bal.round(4).to_csv(out_results / "group_balance_checks.csv", index=False)

    results = {"n": int(len(df)), "assumptions": assume,
               "tests": {k: v for k, v in tests.items() if not k.startswith("_")}}
    (out_results / "results.json").write_text(json.dumps(results, indent=2, default=float), encoding="utf-8")
    write_summary(out_results / "analysis_summary.md", desc, assume, tests, rob, bal, freq, len(df))

    fig_design(out_figures / "00_experimental_design.png")
    fig_means(desc, tests, out_figures / "01_mean_recall_by_condition.png")
    fig_individual(df, desc, out_figures / "02_individual_scores.png")
    fig_distribution(freq, out_figures / "03_score_distribution.png")
    fig_effect(tests, out_figures / "04_effect_size_bootstrap.png")
    fig_robustness(rob, out_figures / "05_robustness_forest_plot.png")
    fig_assumptions(massed, spaced, out_figures / "06_normality_qq_plots.png")
    return {"desc": desc, "freq": freq, "assume": assume, "tests": tests, "robust": rob, "balance": bal}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, default=Path("data/spacing_effect_data.csv"))
    p.add_argument("--out-results", type=Path, default=Path("results"))
    p.add_argument("--out-figures", type=Path, default=Path("figures"))
    a = p.parse_args()
    run(a.data, a.out_results, a.out_figures)
    print(f"Done. See {a.out_results}/analysis_summary.md and {a.out_figures}/")


if __name__ == "__main__":
    main()
