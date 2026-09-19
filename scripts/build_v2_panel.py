"""v2 label-substitution panel (review round 1, 2026-09-19).

Why this exists. In the v1 build (build_benchmark.py) P-scope, P-intensity and
P-indistinct substitute only the filed VALUE: the record presented to the system
keeps the original indicator label, unit and boundary. "Filing says Scope 3 =
6,791.7" against "narrative says Scope 3 = 1,983.9" is then a contradiction by
the task's own rules, and for P-indistinct the record is within tolerance of the
narrative, so SUPPORTED is the rule-conformant answer. NOT_COMPARABLE is not
uniquely correct on those rows and strict accuracy on them is not interpretable.

v2 makes the substitution a substitution of the RECORD: the sibling indicator's
value travels with its own declared label, unit and boundary, and the claim under
audit (indicator + verbatim narrative figure + page) is stated explicitly, so the
decision "do these two denote the same quantity?" is decidable from the inputs and
NOT_COMPARABLE is uniquely correct. P-none controls get the same claim line.

Construction-side script: it may open the v1 ledger. The harness never does.
Deterministic, seed 20260919. No language model anywhere.
"""
import json, math, pathlib, random, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from t3_yield import METRICS
from build_benchmark import (load_filings, SCOPE_SIBLINGS, INTENSITY_PARTNER)

SEED = 20260919
B = pathlib.Path("data/benchmark")
QUOTA = {"P-scope": 25, "P-indistinct": 30, "P-intensity": 15, "P-none": 25}
GOLD = {"P-none": ("SUPPORTED", None),
        "P-scope": ("NOT_COMPARABLE", "scope"),
        "P-indistinct": ("NOT_COMPARABLE", "indistinguishable_metric"),
        "P-intensity": ("NOT_COMPARABLE", "absolute_vs_intensity")}
PCT = {"renewable_share", "female_mgr", "nonmgr_salary_chg", "salary_median_chg",
       "infosec_pii_share", "injury_rate", "fire_cas_share"}


def unit_of(mid: str) -> str:
    """Unit as the platform declares it in the field name."""
    if mid in PCT:
        return "%"
    groups = re.findall(r"\(([^()]*)\)", METRICS[mid][1])
    u = groups[-1] if groups else ""
    return {"噸CO2e": "tCO2e", "噸CO2e/單位": "tCO2e/單位"}.get(u, u)


def sibling_of(L, filings):
    """Recover which indicator's value v1 substituted (the v1 ledger does not
    record it). Exact float match against the company's other filed values."""
    co, mid, t = L["company_id"], L["metric_id"], L["perturbation"]["type"]
    pv = L["filing_presented"]["value"]
    if t == "P-scope":
        cands = SCOPE_SIBLINGS.get(mid, [])
    elif t == "P-intensity":
        cands = [INTENSITY_PARTNER[mid]] if mid in INTENSITY_PARTNER else []
    else:
        cands = [k for k in filings[co] if k != mid]
    hits = [k for k in cands if k in filings[co]
            and math.isclose(filings[co][k]["value"], pv, rel_tol=1e-12)]
    return hits[0] if hits else None


def main():
    rng = random.Random(SEED)
    filings = load_filings()
    ledger = [json.loads(l) for l in (B / "ledger_sealed.jsonl").open(encoding="utf-8")]
    in_tb = {json.loads(l)["item_id"] for l in (B / "eval_tb.jsonl").open(encoding="utf-8")}

    by_type = {t: [] for t in QUOTA}
    for L in ledger:
        t = L["perturbation"]["type"]
        if t in by_type:
            by_type[t].append(L)

    panel, gold, snap, skipped = [], [], {}, 0
    for t, q in QUOTA.items():
        # v1 evaluation items first, so v1 -> v2 can be compared on the same items
        first = [L for L in by_type[t] if L["item_id"] in in_tb]
        rest = [L for L in by_type[t] if L["item_id"] not in in_tb]
        rng.shuffle(rest)
        n = 0
        for L in first + rest:
            if n >= q:
                break
            mid, co = L["metric_id"], L["company_id"]
            if t == "P-none":
                sib = mid
            else:
                sib = sibling_of(L, filings)
                if sib is None:
                    skipped += 1
                    continue
            rec = filings[co][sib]
            iid = L["item_id"] + "@v2"
            fp = {"value": rec["value"], "unit": unit_of(sib), "scope": sib,
                  "consolidation": rec["consolidation"], "period": rec["period"]}
            claim = {"metric_id": mid, "value_verbatim": L["anchor"]["value_verbatim"],
                     "page": L["anchor"]["page"]}
            item = {"item_id": iid, "v1_item_id": L["item_id"], "in_v1_eval": L["item_id"] in in_tb,
                    "company_id": co, "industry": L.get("industry"),
                    "fiscal_year": L.get("fiscal_year"), "metric_id": mid,
                    "anchor": L["anchor"], "claim": claim, "filing_presented": fp}
            panel.append(item)
            v, m = GOLD[t]
            orig = L["perturbation"]["original_value"]
            gold.append({"item_id": iid, "v1_item_id": L["item_id"],
                         "perturbation": {"type": t, "substituted_metric": sib,
                                          "original_value": orig,
                                          "rel_diff": (abs(rec["value"] - orig) / abs(orig)) if orig else None,
                                          "seed": SEED},
                         "gold": {"verdict": v, "mismatch_type": m, "source": "G-C"}})
            snap[iid] = fp
            n += 1
        print(f"{t:14s} quota {q:3d} got {n:3d} (from v1 eval: "
              f"{sum(1 for p in panel if p['item_id'].endswith('@v2') and p['in_v1_eval'] and p['item_id'].split('-P-')[1].startswith(t[2:]))})")

    with (B / "v2_panel.jsonl").open("w", encoding="utf-8") as f:
        for it in panel:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    with (B / "v2_ledger_sealed.jsonl").open("w", encoding="utf-8") as f:
        for g in gold:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    (B / "v2_snapshot.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    assert not any("gold" in it or "perturbation" in it for it in panel)
    print(f"panel {len(panel)} items, skipped (no sibling recovered) {skipped}")


if __name__ == "__main__":
    main()
