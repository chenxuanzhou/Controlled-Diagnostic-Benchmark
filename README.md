# A Controlled Diagnostic Benchmark for Cross-Source Verification of Traditional Chinese ESG Disclosures

Companies listed in Taiwan publish the same sustainability indicator twice: inside a
narrative sustainability report, and as a structured record on the exchange's ESG
platform, where each figure carries a declared data boundary. This repository holds a
benchmark for the decision that redundancy makes checkable: **do the two figures denote
the same quantity, or do only their digits agree?**

Paper: *Matching Digits or Quantities? A Controlled Diagnostic Benchmark for
Cross-Source Verification of Traditional Chinese ESG Disclosures* — C. Zhou, J. Song,
C. J. Liang (University of Technology Sydney). Under review, 2026.

> **Read this first.** Every inconsistency in this benchmark was **injected by us**. No
> item, gold label or model output in this repository describes the actual disclosure
> quality of any company. Model outputs under `out/runs/` reason about *perturbed*
> records; a sentence such as "the filing appears misfiled" refers to our perturbation,
> not to a real filing.

## What is here

| Path | Content |
|---|---|
| `data/benchmark/release_3000.jsonl` | the 3,000 perturbed items (no gold fields) |
| `data/benchmark/eval_tb.jsonl`, `eval_sweep.jsonl` | the evaluated subsets: 235 stratified items, 128-item magnitude sweep |
| `data/benchmark/v2_panel.jsonl` | the 95-item **record-level substitution panel** (claim stated; the substituted record carries its own label) |
| `data/benchmark/ledger_sealed.jsonl`, `v2_ledger_sealed.jsonl` | what was injected, **for the evaluated items only** (358 of the 3,000, and all 95 panel items) |
| `data/benchmark/admissible_r1.jsonl` | **the verdicts the task rules admit — score with this**, see below (same 358 items) |
| `data/anchors/anchor_set.jsonl`, `validity.json` | 3,483 digit-exact anchors (company, indicator, page, span) and the construct-validity numbers |
| `data/structured/` | the exchange's open-data tables as retrieved (public regulatory data) |
| `data/corpus_full/index.json` | the 885 company-years and their report identifiers |
| `config/`, `spec/` | frozen construction rules, tolerance, perturbation mix |
| `scripts/`, `systems/` | construction, the four evaluation conditions (C0, C1, C3, C4), scoring |
| `out/runs/` | raw model outputs of every run reported in the paper |
| `out/tables/`, `out/descriptive/` | the source of every number in the paper |

**Not here:** the 885 sustainability report PDFs (14 GB). They are the issuers' documents
and are not redistributed; `scripts/build_corpus_full.py` downloads them from the
exchange's platform using `data/corpus_full/index.json`.

## Scoring: use admissible verdicts, not the raw ledger label

In the 3,000-item build, three perturbation types (P-scope, P-intensity, P-indistinct)
replace only the filed **value**; the record shown to the system keeps the original
indicator label. "Filing: Scope 1 = B" against "narrative: Scope 1 = A" is then a
contradiction under the task's own rules, so the ledger's `NOT_COMPARABLE` is not
derivable from the inputs. 120/120 P-indistinct and 56/270 P-scope items even lie within
the 1% tolerance of the true filing and are indistinguishable from controls.

`admissible_r1.jsonl` lists, per item, every verdict the rules license for the record as
presented. The record-level panel (`v2_panel.jsonl`) is the clean test of
comparability: there `NOT_COMPARABLE` is uniquely correct, except for 29 items in which
total waste and non-hazardous waste coincide because hazardous waste is filed as zero
(both `SUPPORTED` and `NOT_COMPARABLE` are admissible; `scripts/score_v2.py` reports
them separately).

Gold for the remaining 2,642 items is withheld; contact the authors if you need it to
evaluate a system. "Sealed" is also a property of the harness: a system under test never
opens a ledger file and never sees an item id. Keep it that way when you evaluate your
own system.

## Reproduce the paper's numbers (offline, no API calls)

Everything the paper reports about model behaviour is computed on the evaluated items,
so the published gold is sufficient. Release-wide counts (e.g. how many of the 3,000
items lie within tolerance of the true filing) and `scripts/build_v2_panel.py` need the
full ledger.

```bash
pip install -r requirements.txt
python scripts/rescore_review.py       # -> out/tables/review_r1.json     (main results, McNemar tests)
python scripts/score_v2.py             # -> out/tables/v2_panel.json      (record-level panel, replicates, second model)
python scripts/score_sweep_fixed.py    # -> out/tables/tolerance_sweep_fixed*.json
python scripts/descriptive_study.py    # digit-exact restatement by indicator (needs the PDFs)
```

## Run a model

The runners call an OpenAI-compatible endpoint. Provide your key in the environment
variable `MOONSHOT_API_KEY` (or adapt `systems/llm_client.py`); never commit a key.

```bash
python scripts/run_v2.py c1            # record-level panel, retrieval condition
python scripts/run_v2.py c4            # four-role adversarial pipeline
python scripts/run_sweep_fixed.py      # tolerance sweep
```

## Known limitations

- Gold is constructed, not human-annotated. Digit-exact anchoring scales across unit
  factors without reading the printed unit; among 56 evaluated controls, five pair a
  filing with a narrative figure whose printed unit, definition or stated boundary does
  not match.
- `systems/harness.py::page_text` caches by (company, page) and ignores `limit`; the
  first tolerance sweep was affected. `scripts/run_v2.py` and `scripts/run_sweep_fixed.py`
  use their own page reader.
- `scripts/build_benchmark.py::UNITS` assigns units per table, so 28 of the 235
  evaluated records carry a wrong unit label (e.g. an intensity labelled `tCO2e`).
- P-consolidation draws the replacement boundary from free-text boundaries declared by
  other issuers; success on it is partly foreign-entity detection.
- Two models of one provider; outside the record-level panel, a single run.

## Licence

Code: MIT (`LICENSE`). Benchmark items, anchors, ledgers and result tables: CC BY 4.0.
`data/structured/` reproduces public regulatory open data and remains subject to the
terms of its source platform. Sustainability reports are not included.

## Citation

See `CITATION.cff`. The paper is under review; please check back for the final reference.
