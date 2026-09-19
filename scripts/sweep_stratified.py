"""Tolerance sweep re-read (review round 1).

harness.page_text caches by (company, page) and ignores `limit`. The sweep ran C1
alone, so its anchor page was cut at 733 characters and the anchor figure is
absent from the evidence for some items. This splits the sweep by whether the
anchor token was actually in the evidence the model saw.
Output: out/tables/tolerance_sweep_stratified.json
"""
import collections, json, pathlib, sys
sys.path.insert(0, "scripts")
import pymupdf
from score import parse, wilson

B = pathlib.Path("data/benchmark")
PDF = pathlib.Path("data/corpus_full/raw_pdf")
L = {}
for l in (B / "ledger_sealed.jsonl").open(encoding="utf-8"):
    r = json.loads(l); L[r["item_id"]] = r
items = {json.loads(l)["item_id"]: json.loads(l) for l in (B / "eval_sweep.jsonl").open(encoding="utf-8")}


def seen(it):
    co, pg = it["company_id"], it["anchor"]["page"]
    d = pymupdf.open(PDF / f"{co}_2025.pdf")
    parts = []
    for p in (pg - 1, pg, pg + 1):
        if 1 <= p <= d.page_count:
            parts.append(" ".join(d[p - 1].get_text().split())[:733])
    d.close()
    return "\n---\n".join(parts)


pred = {}
for fn in ("sweep_c1.jsonl", "recover_text.jsonl"):
    for l in (pathlib.Path("out/runs") / fn).open(encoding="utf-8"):
        r = json.loads(l)
        if r["item_id"] in items and "error" not in r:
            v, _ = parse(r.get("content"))
            if v:
                pred[r["item_id"]] = v

cell = collections.defaultdict(collections.Counter)
present = {}
for i, it in items.items():
    present[i] = it["anchor"]["value_verbatim"] in seen(it)
for i, v in pred.items():
    d = abs(L[i]["perturbation"]["delta"])
    side = "below" if d <= 0.01 else "above"
    cell[(side, "anchor_in_evidence" if present[i] else "anchor_cut_off")][v] += 1

out = {"n_items": len(items), "n_with_verdict": len(pred),
       "anchor_in_evidence": sum(present.values()),
       "anchor_cut_off": sum(not x for x in present.values())}
for (side, grp), c in sorted(cell.items()):
    n = sum(c.values()); k = c["SUPPORTED"]
    out[f"{side}|{grp}"] = {"dist": dict(c), "supported": k, "n": n,
                            "rate": round(k / n, 4), "ci": [round(x, 3) for x in wilson(k, n)]}
pathlib.Path("out/tables/tolerance_sweep_stratified.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1))
