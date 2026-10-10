#!/usr/bin/env python3
"""Create the pseudonymised analysis dataset from the raw collection workbook.

The raw workbook contains participant names and is NEVER committed to this
repository (see .gitignore). This script documents exactly how the published
file ``data/spacing_effect_data.csv`` was derived from it:

1. keep only rows that contain a completed session (blank placeholder rows dropped)
2. strip stray whitespace from categorical fields
3. drop direct identifiers (name) and fields not used in the analysis (session date, notes)
4. replace the original participant IDs with random study IDs (P01-P36) and the
   original data-collector prefixes with neutral labels (R1-R4), using a fixed seed

Usage:
    python analysis/prepare_data.py --input path/to/Spacing_Effect_Raw_Data.xlsx
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 2026
SCORE_COL = "Words Recalled (out of 20)"


def build_dataset(raw_path: Path) -> pd.DataFrame:
    raw = pd.read_excel(raw_path, sheet_name="Raw Data")
    df = raw.dropna(subset=["Group", SCORE_COL]).copy()

    for col in ("Group", "Gender"):
        df[col] = df[col].astype(str).str.strip()

    df["collector_prefix"] = df["Participant ID"].astype(str).str[0]
    df["year_of_study"] = df["Year of Study"].str.extract(r"(\d)").astype(int)

    rng = np.random.default_rng(SEED)

    # random study IDs, unrelated to collection order
    order = rng.permutation(len(df))
    df["participant_id"] = [f"P{n + 1:02d}" for n in order]

    # neutral data-collector labels
    prefixes = sorted(df["collector_prefix"].unique())
    shuffled = rng.permutation(len(prefixes))
    mapping = {p: f"R{i + 1}" for p, i in zip(prefixes, shuffled)}
    df["researcher"] = df["collector_prefix"].map(mapping)

    out = pd.DataFrame(
        {
            "participant_id": df["participant_id"],
            "condition": df["Group"],
            "researcher": df["researcher"],
            "age": df["Age"].astype(int),
            "gender": df["Gender"],
            "year_of_study": df["year_of_study"],
            "words_recalled": df[SCORE_COL].astype(int),
        }
    )
    return out.sort_values("participant_id").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path, help="raw workbook (.xlsx) - keep this file private")
    parser.add_argument("--output", type=Path, default=Path("data/spacing_effect_data.csv"))
    args = parser.parse_args()

    out = build_dataset(args.input)
    assert len(out) == 36 and out["condition"].value_counts().eq(18).all(), "unexpected sample structure"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)
    print(f"Wrote {len(out)} rows to {args.output}")


if __name__ == "__main__":
    main()
