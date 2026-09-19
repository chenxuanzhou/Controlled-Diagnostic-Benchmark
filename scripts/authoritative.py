"""Single authoritative scoring pass. Every number quoted in the paper must be
traceable to out/tables/authoritative.json produced here.

Two panels:
  full    -- each condition on every item it was run on (n differs by condition)
  paired  -- the intersection of items with a parseable response in ALL of
             C0, C1, C3, C4, so cross-condition comparisons are like-for-like
"""
import collections, json, math, pathlib, sys
sys.path.insert(0, "scripts")
from score import load_gold, parse, wilson

RUNS = pathlib.Path("out/runs")
OUT = pathlib.Path("out/tables"); OUT.mkdir(parents=True, exist_ok=True)

SOURCES = [
    ("C0",                 "tb_text.jsonl", "C0"),
    ("C1",                 "tb_text.jsonl", "C1"),
    ("C3",                 "tb_c3.jsonl",   None),
    ("C4",                 "tb_c4.jsonl",   None),
    ("C3-calc",            "tb_abl_calc.jsonl",   None),
    ("C3-filing_lookup",   "tb_abl_lookup.jsonl", None),
]


def load(fname, cond):
    p = RUNS / fname
    if not p.exists():
        return []
    out = []
    for l in p.open(encoding="utf-8"):
        r = json.loads(l)
        if cond is not None and r.get("condition") != cond:
            continue
        out.append(r)
    return out


def predictions(rows):
    """item_id -> (verdict, mismatch_type) for rows that parsed."""
    d = {}
    for r in rows:
        if "error" in r:
            continue
        v, mm = parse(r.get("content"))
        if v is not None:
            d[r["item_id"]] = (v, mm)
    return d


def stats(preds, gold, keep=None):
    ids = [i for i in preds if i in gold and (keep is None or i in keep)]
    n = len(ids)
    correct = sum(preds[i][0] == gold[i]["verdict"] for i in ids)
    nc = [i for i in ids if gold[i]["verdict"] == "NOT_COMPARABLE"]
    over = sum(preds[i][0] in ("SUPPORTED", "CONTRADICTED") for i in nc)
    tp = sum(gold[i]["verdict"] == "NOT_COMPARABLE" and preds[i][0] == "NOT_COMPARABLE" for i in ids)
    fp = sum(gold[i]["verdict"] != "NOT_COMPARABLE" and preds[i][0] == "NOT_COMPARABLE" for i in ids)
    fn = sum(gold[i]["verdict"] == "NOT_COMPARABLE" and preds[i][0] != "NOT_COMPARABLE" for i in ids)
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0

    byp, tol, mm = collections.defaultdict(lambda: [0, 0]), collections.defaultdict(lambda: [0, 0]), collections.Counter()
    pred_dist = collections.defaultdict(collections.Counter)
    for i in ids:
        g, (p, pmm) = gold[i], preds[i]
        byp[g["ptype"]][1] += 1
        byp[g["ptype"]][0] += p == g["verdict"]
        pred_dist[g["ptype"]][p] += 1
        if g["mismatch_type"]:
            mm[(g["mismatch_type"], pmm)] += 1
        if g["ptype"] == "P-magnitude" and g["delta"] is not None:
            k = round(abs(g["delta"]) * 100, 1)
            tol[k][1] += 1
            tol[k][0] += p == "SUPPORTED"
    return {
        "n": n,
        "accuracy": round(correct / n, 4) if n else None,
        "acc_ci": [round(x, 4) for x in wilson(correct, n)],
        "overclaim": round(over / len(nc), 4) if nc else None,
        "overclaim_n": len(nc),
        "abstention": {"precision": round(pr, 4), "recall": round(rc, 4),
                       "f1": round(2*pr*rc/(pr+rc), 4) if pr+rc else 0.0,
                       "tp": tp, "fp": fp, "fn": fn},
        "by_ptype": {k: {"acc": round(v[0]/v[1], 4), "n": v[1],
                         "ci": [round(x, 4) for x in wilson(v[0], v[1])]}
                     for k, v in sorted(byp.items())},
        "pred_dist_by_ptype": {k: dict(v) for k, v in sorted(pred_dist.items())},
        "tolerance": {str(k): {"supported": v[0], "n": v[1],
                               "rate": round(v[0]/v[1], 4),
                               "ci": [round(x, 4) for x in wilson(v[0], v[1])]}
                      for k, v in sorted(tol.items())},
        "mismatch_confusion": {f"{a}->{b}": c for (a, b), c in sorted(mm.items(), key=lambda x: (x[0][0], str(x[0][1])))},
    }


def main():
    gold = load_gold()
    raw = {name: load(f, c) for name, f, c in SOURCES}
    preds = {k: predictions(v) for k, v in raw.items()}

    core = ["C0", "C1", "C3", "C4"]
    paired_ids = set.intersection(*(set(preds[c]) for c in core))
    print(f"paired intersection over {core}: n = {len(paired_ids)}")

    res = {
        "gold_source": "data/benchmark/ledger_sealed.jsonl",
        "paired_conditions": core,
        "paired_n": len(paired_ids),
        "full": {k: dict(stats(preds[k], gold),
                         calls=len(raw[k]),
                         errors=sum(1 for r in raw[k] if "error" in r),
                         unparsed=sum(1 for r in raw[k]
                                      if "error" not in r and parse(r.get("content"))[0] is None))
                 for k in preds},
        "paired": {k: stats(preds[k], gold, keep=paired_ids) for k in core},
    }
    # ablation is only meaningful against C3 on ITS own items
    abl_ids = set.intersection(*(set(preds[c]) for c in ("C3", "C3-calc", "C3-filing_lookup")))
    res["ablation_paired_n"] = len(abl_ids)
    res["ablation_paired"] = {k: stats(preds[k], gold, keep=abl_ids)
                              for k in ("C3", "C3-calc", "C3-filing_lookup")}
    print(f"ablation intersection: n = {len(abl_ids)}")

    (OUT / "authoritative.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{'condition':20}{'full n':>8}{'acc':>8}{'overcl':>8}   |{'paired n':>9}{'acc':>8}{'overcl':>8}")
    for k in preds:
        f = res["full"][k]
        p = res["paired"].get(k)
        line = f"{k:20}{f['n']:>8}{f['accuracy']:>8.3f}"
        line += f"{f['overclaim']:>8.3f}" if f["overclaim"] is not None else f"{'-':>8}"
        if p:
            line += f"   |{p['n']:>9}{p['accuracy']:>8.3f}"
            line += f"{p['overclaim']:>8.3f}" if p["overclaim"] is not None else f"{'-':>8}"
        print(line)
    print(f"\n-> {OUT/'authoritative.json'}")


if __name__ == "__main__":
    main()
