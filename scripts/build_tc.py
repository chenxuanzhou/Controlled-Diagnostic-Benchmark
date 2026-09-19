"""T-C: filing internal consistency (gold source G-A).

Deterministic invariants over one company's own filed record. No narrative, no
model, no judgement -- a violation is arithmetic, not opinion.

Which invariants are actually checkable is constrained by what the platform
collects. There is no filed ghg_total and no filed denominator for the intensity
fields, so spec v2 §3's first and third example invariants cannot be evaluated;
what remains is stated below and is checked exactly.

TASK-01 ambiguity #14 is the motivating observation: 環泥 files scopes 1-3 on a
parent-only basis while declaring a consolidated boundary, and its intensity
matches the consolidated total -- one record, two bases.
"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from t3_yield import _load, _num

SEED = 20260914
TOL = 0.01           # 1%, the frozen evaluation epsilon
OUT = pathlib.Path("data/benchmark"); OUT.mkdir(parents=True, exist_ok=True)

INVARIANTS = [
    ("waste_additivity",
     "有害廢棄物量 + 非有害廢棄物量 = 總重量(有害+非有害)"),
    ("waste_ordering",
     "總重量 >= 有害廢棄物量 且 總重量 >= 非有害廢棄物量"),
    ("waste_boundary_consistency",
     "三個廢棄物欄位的資料範圍應相同，否則總量不是同一口徑下的分項之和"),

    ("infosec_implication",
     "受影響顧客數 > 0 蘊含 資訊外洩事件數量 > 0"),
    ("fire_implication",
     "火災死傷人數 > 0 蘊含 火災件數 > 0"),
]


def build():
    t4 = {r["公司代號"]: r for r in _load(4)}
    t1 = {r["公司代號"]: r for r in _load(1)}
    t16 = {r["公司代號"]: r for r in _load(16)}
    t21 = {r["公司代號"]: r for r in _load(21)}
    idx = json.loads(pathlib.Path("data/corpus_full/index.json").read_text(encoding="utf-8"))
    ind = {r["company_id"]: r["industry"] for r in idx}

    items, heterogeneous = [], []
    for code in sorted(set(t4) | set(t1)):
        w, g = t4.get(code, {}), t1.get(code, {})
        s16, s21 = t16.get(code, {}), t21.get(code, {})
        hz = _num(w.get("有害廢棄物量-數據(公噸) "))
        nh = _num(w.get("非有害廢棄物量-數據(公噸)"))
        tt = _num(w.get("總重量(有害+非有害)-數據(公噸)"))
        checks = []

        if None not in (hz, nh, tt) and tt:
            d = abs((hz + nh) - tt) / abs(tt)
            checks.append({"invariant": "waste_additivity", "violated": d > TOL,
                           "detail": {"hazard": hz, "nonhazard": nh, "total": tt,
                                      "rel_error": round(d, 6)}})
            checks.append({"invariant": "waste_ordering",
                           "violated": not (tt >= hz - 1e-9 and tt >= nh - 1e-9),
                           "detail": {"hazard": hz, "nonhazard": nh, "total": tt}})

        bs = [w.get("有害廢棄物量-資料範圍"), w.get("非有害廢棄物量-資料範圍"),
              w.get("總重量(有害+非有害)-資料範圍")]
        bs = [b for b in bs if b]
        if len(bs) >= 2:
            checks.append({"invariant": "waste_boundary_consistency",
                           "violated": len(set(bs)) > 1,
                           "detail": {"boundaries": bs}})

        # NOT an invariant: filing scope 1 and scope 2 over different inventory
        # boundaries is permitted, so a mismatch is an observation, not a
        # violation. Counting it as gold would smuggle judgement into G-A.
        b1, b2 = g.get("範疇一資料邊界"), g.get("範疇二資料邊界")
        if b1 and b2 and b1 != b2:
            heterogeneous.append({"company_id": code, "industry": ind.get(code, ""),
                                  "scope1_boundary": b1, "scope2_boundary": b2})

        inc = _num(s16.get("資訊外洩事件數量"))
        aff = _num(s16.get("因資訊外洩事件而受影響的顧客數(人)"))
        if inc is not None and aff is not None:
            checks.append({"invariant": "infosec_implication",
                           "violated": aff > 0 and inc == 0,
                           "detail": {"incidents": inc, "affected": aff}})

        fc = _num(s21.get("火災件數(件)"))
        fk = _num(s21.get("火災死傷人數(人)"))
        if fc is not None and fk is not None:
            checks.append({"invariant": "fire_implication",
                           "violated": fk > 0 and fc == 0,
                           "detail": {"fires": fc, "casualties": fk}})

        for c in checks:
            items.append({
                "item_id": f"{code}-2025-TC-{c['invariant']}",
                "company_id": code, "industry": ind.get(code, ""),
                "fiscal_year": 2025, "invariant": c["invariant"],
                "filing_fields": c["detail"],
                "gold": {"verdict": "VIOLATION" if c["violated"] else "CONSISTENT",
                         "source": "G-A"},
            })
    return items, heterogeneous


def main():
    items, hetero = build()
    tot = len(items)
    viol = sum(1 for i in items if i["gold"]["verdict"] == "VIOLATION")
    by = {}
    for i in items:
        d = by.setdefault(i["invariant"], {"n": 0, "violations": 0})
        d["n"] += 1
        d["violations"] += i["gold"]["verdict"] == "VIOLATION"

    with (OUT / "tc_all.jsonl").open("w", encoding="utf-8") as f:
        for i in items:
            f.write(json.dumps(i, ensure_ascii=False) + "\n")
    (OUT / "tc_stats.json").write_text(json.dumps(
        {"n_checks": tot, "n_violations": viol,
         "violation_rate": round(viol / max(tot, 1), 4),
         "by_invariant": {k: {**v, "rate": round(v["violations"] / v["n"], 4)}
                          for k, v in by.items()},
         "invariant_definitions": dict(INVARIANTS),
         "not_checkable": ["scope1+scope2+scope3 = ghg_total (no filed total)",
                           "intensity x denominator = absolute (no filed denominator)"],
         "excluded_as_not_definitional": {
             "ghg_boundary_heterogeneity": {
                 "n_companies": len(hetero),
                 "why": ("inventorying scope 1 and scope 2 over different boundaries is "
                         "permitted; a mismatch is an observation, not a rule violation. "
                         "Counting it as gold would put judgement into G-A (INV-8).")}},
         "tolerance": TOL, "gold_source": "G-A"},
        ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{'invariant':32}{'n':>7}{'violations':>12}{'rate':>8}")
    for k, v in sorted(by.items(), key=lambda x: -x[1]["violations"] / max(x[1]["n"], 1)):
        print(f"{k:32}{v['n']:>7}{v['violations']:>12}{v['violations']/v['n']*100:>7.1f}%")
    (OUT / "ghg_boundary_heterogeneity.json").write_text(json.dumps(
        {"n_companies": len(hetero),
         "note": ("descriptive only, NOT gold: inventorying scope 1 and scope 2 over "
                  "different boundaries is permitted, so a mismatch is an observation, "
                  "not a rule violation (INV-8)."),
         "rows": hetero}, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\ntotal definitional checks {tot}, violations {viol} ({viol/tot*100:.2f}%)")
    print(f"separately recorded (NOT gold): {len(hetero)} companies file scope 1 and "
          f"scope 2 on different boundaries")
    print(f"-> {OUT/'tc_all.jsonl'}, {OUT/'tc_stats.json'}, "
          f"{OUT/'ghg_boundary_heterogeneity.json'}")


if __name__ == "__main__":
    main()
