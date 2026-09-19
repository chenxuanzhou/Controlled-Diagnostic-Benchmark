"""Score the rerun tolerance sweep (out/runs/sweep_c1_fixed.jsonl).
Output: out/tables/tolerance_sweep_fixed.json  (same shape as tolerance_sweep.json,
plus the verdict distribution per magnitude and the signed split)."""
import collections, json, pathlib, sys
sys.path.insert(0, "scripts")
from score import parse, wilson

L = {}
for l in open("data/benchmark/ledger_sealed.jsonl", encoding="utf-8"):
    r = json.loads(l); L[r["item_id"]] = r
pred = {}
for l in open("out/runs/sweep_c1_fixed.jsonl", encoding="utf-8"):
    r = json.loads(l)
    if "error" in r:
        continue
    v, _ = parse(r.get("content"))
    if v:
        pred[r["item_id"]] = v
cell = collections.defaultdict(collections.Counter); signed = collections.defaultdict(collections.Counter)
for i, v in pred.items():
    d = L[i]["perturbation"]["delta"]
    cell[round(abs(d) * 100, 1)][v] += 1
    signed[(round(abs(d) * 100, 1), "+" if d > 0 else "-")][v] += 1
out = {}
for k in sorted(cell):
    c = cell[k]; n = sum(c.values()); s = c["SUPPORTED"]
    out[str(k)] = {"supported": s, "n": n, "rate": round(s / n, 4),
                   "ci": [round(x, 4) for x in wilson(s, n)], "dist": dict(c)}
below = [k for k in cell if k <= 1.0]; above = [k for k in cell if k > 1.0]
summ = {"n_items": 128, "n_with_verdict": len(pred),
        "below_eps": {"supported": sum(cell[k]["SUPPORTED"] for k in below), "n": sum(sum(cell[k].values()) for k in below),
                      "dist": dict(sum((cell[k] for k in below), collections.Counter()))},
        "above_eps": {"supported": sum(cell[k]["SUPPORTED"] for k in above), "n": sum(sum(cell[k].values()) for k in above),
                      "dist": dict(sum((cell[k] for k in above), collections.Counter()))},
        "signed": {f"{k[0]}{k[1]}": dict(v) for k, v in sorted(signed.items())}}
for g in ("below_eps", "above_eps"):
    summ[g]["ci"] = [round(x, 3) for x in wilson(summ[g]["supported"], summ[g]["n"])]
pathlib.Path("out/tables/tolerance_sweep_fixed.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
pathlib.Path("out/tables/tolerance_sweep_fixed_summary.json").write_text(json.dumps(summ, indent=1, ensure_ascii=False), encoding="utf-8")
print(json.dumps(summ, ensure_ascii=False, indent=1))
for k, v in out.items():
    print(k, v["supported"], "/", v["n"], v["dist"])
