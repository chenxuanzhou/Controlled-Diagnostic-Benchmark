"""Camera-ready (reviewer H7p2, concern 1): sensitivity of the cross-condition claims
to missing outputs. Offline; no API calls. Output: out/tables/sensitivity_missing.json

3,000-item build. C3 and C4 were run on a 120-item prefix of the 235-item subset,
C0 and C1 on all 235. On the 120 prefix items every condition was attempted, so a
missing verdict can be scored instead of dropped:
  wrong   -- a missing verdict counts as an error (the reviewer's suggestion)
  right   -- a missing verdict counts as correct (upper bound for that condition)
  adverse -- the most unfavourable case for "C1 > C4": C1's missing wrong, C4's right
Record-level panel. The C4 affirmation count can only grow if a missing verdict is
imputed as SUPPORTED; we report both ends.
"""
import json, pathlib, sys
sys.path.insert(0, "scripts")
from rescore_review import ledger, admissible, mcnemar, B, RUNS
from authoritative import load, predictions, SOURCES
from score import parse, wilson

OUT = pathlib.Path("out/tables/sensitivity_missing.json")


def v1():
    L = ledger()
    raw = {name: load(f, c) for name, f, c in SOURCES if name in ("C0", "C1", "C3", "C4")}
    preds = {k: predictions(v) for k, v in raw.items()}
    attempted = {k: {r["item_id"] for r in v} for k, v in raw.items()}
    prefix = attempted["C3"] & attempted["C4"]
    assert attempted["C3"] == attempted["C4"], "C3 and C4 were run on different items"
    assert prefix <= attempted["C0"] and prefix <= attempted["C1"]
    order = sorted(prefix)
    res = {"prefix_n": len(prefix),
           "missing_on_prefix": {c: sum(i not in preds[c] for i in order) for c in preds}}

    def ok(c, i, policy):
        if i in preds[c]:
            return preds[c][i][0] in admissible(L[i])
        if policy == "wrong":
            return False
        if policy == "right":
            return True
        return c == "C4"            # adverse to the claim C1 > C4

    for policy in ("wrong", "right", "adverse"):
        row = {}
        for c in ("C0", "C1", "C3", "C4"):
            k = sum(ok(c, i, policy) for i in order)
            row[c] = {"k": k, "n": len(order), "acc": round(k / len(order), 4),
                      "ci": [round(x, 3) for x in wilson(k, len(order))]}
        for a, b in (("C1", "C4"), ("C1", "C3"), ("C3", "C4"), ("C0", "C4")):
            x = mcnemar([ok(a, i, policy) for i in order], [ok(b, i, policy) for i in order])
            row[f"mcnemar_{a}_vs_{b}"] = {"a_only": x[0], "b_only": x[1], "p": x[2]}
        res[policy] = row

    # answered-only accuracy on the prefix, for comparison with the paired panel
    for c in ("C0", "C1", "C3", "C4"):
        ids = [i for i in order if i in preds[c]]
        k = sum(preds[c][i][0] in admissible(L[i]) for i in ids)
        res.setdefault("answered_only", {})[c] = {"k": k, "n": len(ids), "acc": round(k / len(ids), 4)}

    # false abstention on the prefix, counting a missing verdict as an abstention (worst case)
    non_nc = [i for i in order if "NOT_COMPARABLE" not in admissible(L[i])]
    fa = {}
    for c in ("C0", "C1", "C3", "C4"):
        nc = sum(1 for i in non_nc if i in preds[c] and preds[c][i][0] == "NOT_COMPARABLE")
        miss = sum(1 for i in non_nc if i not in preds[c])
        fa[c] = {"nc": nc, "missing": nc + miss - nc, "n": len(non_nc),
                 "rate_answered": round(nc / max(1, len(non_nc) - miss), 4),
                 "rate_missing_as_abstention": round((nc + miss) / len(non_nc), 4)}
    res["false_abstention_prefix"] = fa

    # which perturbation types are missing, per condition (is missingness concentrated?)
    by_type = {}
    for c in ("C0", "C1", "C3", "C4"):
        d = {}
        for i in order:
            if i not in preds[c]:
                t = L[i]["perturbation"]["type"]
                d[t] = d.get(t, 0) + 1
        by_type[c] = dict(sorted(d.items()))
    res["missing_by_type_prefix"] = by_type
    return res


def v2():
    G = {json.loads(l)["item_id"]: json.loads(l) for l in (B / "v2_ledger_sealed.jsonl").open(encoding="utf-8")}
    preds, attempted = {}, {}
    for c in ("c1", "c3", "c4"):
        rows = [json.loads(l) for l in (RUNS / f"v2_{c}.jsonl").open(encoding="utf-8")]
        attempted[c.upper()] = {r["item_id"] for r in rows}
        d = {}
        for r in rows:
            if "error" in r:
                continue
            v, mm = parse(r.get("content"))
            if v is not None:
                d[r["item_id"]] = (v, mm)
        preds[c.upper()] = d
    differ = sorted(i for i, g in G.items() if g["gold"]["verdict"] == "NOT_COMPARABLE"
                    and g["perturbation"].get("rel_diff") not in (0, None)
                    and abs(g["perturbation"]["rel_diff"]) > 0.01)
    res = {"values_differ_n": len(differ)}
    for c in preds:
        ans = [i for i in differ if i in preds[c]]
        aff = sum(preds[c][i][0] == "SUPPORTED" for i in ans)
        miss = len(differ) - len(ans)
        res[c] = {"answered": len(ans), "missing": miss, "affirmed": aff,
                  "affirmed_if_missing_not_affirmed": [aff, len(differ)],
                  "affirmed_if_missing_affirmed": [aff + miss, len(differ)]}
    # C1 vs C4 on all values-differ items, a missing verdict counted as wrong for both
    okc = lambda c, i: i in preds[c] and preds[c][i][0] == "NOT_COMPARABLE"
    x = mcnemar([okc("C1", i) for i in differ], [okc("C4", i) for i in differ])
    res["mcnemar_C1_vs_C4_missing_wrong"] = {"a_only": x[0], "b_only": x[1], "p": x[2]}
    return res


if __name__ == "__main__":
    out = {"v1_prefix": v1(), "v2_panel": v2()}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
