# Data dictionary — `spacing_effect_data.csv`

One row per participant (N = 36). No missing values.

| Column | Type | Values | Description |
|---|---|---|---|
| `participant_id` | string | `P01`–`P36` | Random study ID, unrelated to collection order or the original ID scheme |
| `condition` | categorical | `Massed`, `Spaced` | Between-subjects study schedule (independent variable) |
| `researcher` | categorical | `R1`–`R4` | Team member who ran the session (neutral label) |
| `age` | integer | 22–26 | Age in years |
| `gender` | categorical | `Male`, `Female` | Self-reported gender |
| `year_of_study` | integer | 2, 3, 4 | Undergraduate year |
| `words_recalled` | integer | 0–20 | Words correctly recalled out of 20 (dependent variable) |

## Provenance and de-identification

The raw collection workbook (participant names, original IDs, session dates, notes) is **not** part of this repository.
`analysis/prepare_data.py` documents exactly how this file was derived from it:

- completed sessions only (blank placeholder rows removed)
- names, session dates and free-text notes removed
- original participant IDs and data-collector prefixes replaced by randomised labels (fixed seed)
- whitespace in categorical fields normalised (e.g. `"Male "` → `Male`)

## Scoring rule

Recall sheets were scored against a predetermined answer key; minor spelling mistakes were counted correct when the intended word was clear (rule agreed before scoring began).
