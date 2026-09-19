"""TASK-05R: perturbation injection, sealed ledger, and evaluation subsets.

gold source = G-C (the ledger). The truth is the generation process itself, so no
judgement enters anywhere. INV-9: the ledger is written to a separate file that
the evaluation harness never opens; filing_lookup serves the PERTURBED snapshot.

One anchor may spawn several perturbed items. That is the contrast-set design
(Gardner et al., 2020): holding the narrative fixed and varying only the filing
is what isolates the effect of each mismatch type.
"""
import json, math, pathlib, random, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from t3_yield import METRICS, _load, _num

SEED = 20260914
CFG = json.loads(pathlib.Path("config/perturbation_mix.json").read_text(encoding="utf-8"))
EPS = json.loads(pathlib.Path("config/epsilon.json").read_text(encoding="utf-8"))["epsilon"]
MIX = CFG["mix"]
GRID = MIX["P-magnitude"]["grid_pct"]
OUT = pathlib.Path("data/benchmark"); OUT.mkdir(parents=True, exist_ok=True)

BOUNDARY_FIELD = {
    "ghg_scope1": "範疇一資料邊界", "ghg_scope2": "範疇二資料邊界",
    "ghg_scope3": "範疇三資料邊界", "ghg_intensity": "範疇一資料邊界",
    "renewable_share": "資料範圍", "water_use": "資料範圍", "water_intensity": "資料範圍",
    "waste_hazard": "有害廢棄物量-資料範圍", "waste_nonhazard": "非有害廢棄物量-資料範圍",
    "waste_total": "總重量(有害+非有害)-資料範圍",
}
INTENSITY_PARTNER = {          # absolute <-> intensity pairs for P-intensity
    "ghg_scope1": "ghg_intensity", "ghg_intensity": "ghg_scope1",
    "water_use": "water_intensity", "water_intensity": "water_use",
    "waste_total": "waste_intensity", "waste_intensity": "waste_total",
}
SCOPE_SIBLINGS = {             # same-family alternates for P-scope
    "ghg_scope1": ["ghg_scope2", "ghg_scope3"],
    "ghg_scope2": ["ghg_scope1", "ghg_scope3"],
    "ghg_scope3": ["ghg_scope1", "ghg_scope2"],
    "waste_hazard": ["waste_nonhazard", "waste_total"],
    "waste_nonhazard": ["waste_hazard", "waste_total"],
    "waste_total": ["waste_hazard", "waste_nonhazard"],
}


def load_filings():
    tabs = {t: _load(t) for t in {m[0] for m in METRICS.values()}}
    by_co = {}
    for mid, (t, field, _v) in METRICS.items():
        for rec in tabs[t]:
            v = _num(rec.get(field))
            if v is None or v == 0:
                continue
            d = by_co.setdefault(rec["公司代號"], {})
            d[mid] = {"value": v, "period": rec["報告年度"],
                      "consolidation": rec.get(BOUNDARY_FIELD.get(mid, ""), "") or ""}
    return by_co


def all_boundaries(filings):
    s = set()
    for d in filings.values():
        for r in d.values():
            if r["consolidation"]:
                s.add(r["consolidation"])
    return sorted(s)


def perturb(anchor, filings, boundaries, rng, ptype, unit):
    """Return (filing_presented, gold) for one perturbation type."""
    co, mid = anchor["company_id"], anchor["metric_id"]
    base = filings[co][mid]
    v, cons, period = base["value"], base["consolidation"], base["period"]
    fp = {"value": v, "unit": unit, "scope": mid,
          "consolidation": cons, "period": period}
    pert = {"type": ptype, "delta": None, "original_value": v, "seed": SEED}

    if ptype == "P-none":
        return fp, {"verdict": "SUPPORTED", "mismatch_type": None, "source": "G-C"}, pert

    if ptype == "P-magnitude":
        d = rng.choice(GRID) / 100.0 * rng.choice([1, -1])
        fp["value"] = v * (1 + d)
        pert["delta"] = round(d, 6)
        verdict = "SUPPORTED" if abs(d) <= EPS else "CONTRADICTED"
        return fp, {"verdict": verdict, "mismatch_type": None, "source": "G-C"}, pert

    if ptype == "P-consolidation":
        alts = [b for b in boundaries if b != cons]
        fp["consolidation"] = rng.choice(alts) if alts else "已完成母公司"
        return fp, {"verdict": "NOT_COMPARABLE", "mismatch_type": "consolidation",
                    "source": "G-C"}, pert

    if ptype == "P-intensity":
        partner = INTENSITY_PARTNER.get(mid)
        pv = filings[co].get(partner, {}).get("value") if partner else None
        if pv is None:
            return None, None, None
        fp["value"] = pv
        return fp, {"verdict": "NOT_COMPARABLE", "mismatch_type": "absolute_vs_intensity",
                    "source": "G-C"}, pert

    if ptype == "P-scope":
        sibs = [s for s in SCOPE_SIBLINGS.get(mid, []) if s in filings[co]]
        if not sibs:
            return None, None, None
        s = rng.choice(sibs)
        fp["value"] = filings[co][s]["value"]
        return fp, {"verdict": "NOT_COMPARABLE", "mismatch_type": "scope", "source": "G-C"}, pert

    if ptype == "P-indistinct":
        near = [(k, r["value"]) for k, r in filings[co].items()
                if k != mid and r["value"] and abs(r["value"] - v) / abs(v) < 0.001]
        if not near:
            return None, None, None
        fp["value"] = rng.choice(near)[1]
        return fp, {"verdict": "NOT_COMPARABLE", "mismatch_type": "indistinguishable_metric",
                    "source": "G-C"}, pert

    if ptype == "P-unit":
        fp["value"] = v * 1e3
        return fp, {"verdict": "CONTRADICTED", "mismatch_type": None, "source": "G-C"}, pert

    if ptype == "P-null":
        fp["value"] = None
        return fp, {"verdict": "NOT_APPLICABLE", "mismatch_type": None, "source": "G-C"}, pert

    if ptype == "P-crosscompany":
        others = [c for c in filings if c != co and mid in filings[c]]
        if not others:
            return None, None, None
        o = rng.choice(others)
        fp["value"] = filings[o][mid]["value"]
        fp["consolidation"] = filings[o][mid]["consolidation"]
        pert["source_company"] = o
        return fp, {"verdict": "NOT_COMPARABLE", "mismatch_type": "cross_company",
                    "source": "G-C"}, pert

    raise ValueError(ptype)


UNITS = {1: "tCO2e", 2: "%", 3: "公噸", 4: "公噸", 5: "仟元/人", 16: "件", 21: "人"}


def main(n_release=3000):
    rng = random.Random(SEED)
    anchors = [json.loads(l) for l in
               open("data/anchors/anchor_set.jsonl", encoding="utf-8")]
    print(f"anchors loaded: {len(anchors)}")
    filings = load_filings()
    boundaries = all_boundaries(filings)
    print(f"companies with filings: {len(filings)}   distinct boundary labels: {len(boundaries)}")

    types = list(MIX)
    # Quota-driven generation. Random type sampling wastes the scarce types:
    # P-intensity needs an absolute/intensity partner and P-indistinct needs a
    # near-duplicate metric, and neither exists for most anchors. Walking every
    # anchor per type takes all the constructible ones instead of ~4% of them.
    rel, ledger, seen = [], [], set()
    capacity = {}
    for t in types:
        quota = round(MIX[t]["share"] * n_release)
        made = 0
        for a in anchors:
            if made >= quota:
                break
            key = (a["company_id"], a["metric_id"], t)
            if key in seen:
                continue
            unit = UNITS[METRICS[a["metric_id"]][0]]
            try:
                fp, gold, pert = perturb(a, filings, boundaries, rng, t, unit)
            except Exception:
                continue
            if fp is None:
                continue
            seen.add(key)
            iid = f"{a['company_id']}-2025-{a['metric_id']}-{t}"
            item = {"item_id": iid, "company_id": a["company_id"],
                    "industry": a.get("industry", ""), "fiscal_year": 2025,
                    "metric_id": a["metric_id"],
                    "anchor": {k: a["anchor"][k] for k in
                               ("page", "span", "value_verbatim", "sig_digits", "anchor_offset")},
                    "filing_presented": fp}
            rel.append(item)
            ledger.append({**item, "perturbation": pert, "gold": gold})
            made += 1
        capacity[t] = {"quota": quota, "made": made,
                       "shortfall": quota - made,
                       "constructible_on_all_anchors": made >= quota}
        print(f"  {t:16} quota={quota:4}  made={made:4}"
              f"{'' if made>=quota else '   SHORT by %d' % (quota-made)}")

    pathlib.Path("data/benchmark/capacity.json").write_text(
        json.dumps(capacity, ensure_ascii=False, indent=1), encoding="utf-8")

    with (OUT / "release_3000.jsonl").open("w", encoding="utf-8") as f:
        for it in rel:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    with (OUT / "ledger_sealed.jsonl").open("w", encoding="utf-8") as f:
        for it in ledger:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"release set: {len(rel)}  ->  {OUT/'release_3000.jsonl'}")
    print(f"sealed ledger: {len(ledger)}  ->  {OUT/'ledger_sealed.jsonl'}")
    return rel, ledger


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3000)
