"""TASK-05R steps 3-4: evaluation subsets, the sealed snapshot, and Gate G-SEAL.

Two subsets, because they answer different questions and the budget cannot
afford one set that does both:

  eval_tb    balanced across perturbation types  -> Tab.3, Tab.4, Fig.3
  eval_sweep all P-magnitude, dense over the delta grid -> Fig.6

Sizes follow config/model_matrix.json, which was fixed against a hard 100 RMB
budget; they are smaller than spec v2's nominal 600.
"""
import collections, json, pathlib, random, sys

SEED = 20260914
OUT = pathlib.Path("data/benchmark")
SYS = pathlib.Path("systems"); SYS.mkdir(exist_ok=True)
GOLD_KEYS = {"gold", "perturbation"}


def main(n_tb=235, n_sweep=128, per_cell=8):
    rng = random.Random(SEED)
    ledger = [json.loads(l) for l in (OUT / "ledger_sealed.jsonl").open(encoding="utf-8")]
    by_id = {x["item_id"]: x for x in ledger}
    release = [json.loads(l) for l in (OUT / "release_3000.jsonl").open(encoding="utf-8")]

    # ---- eval_tb: proportional to the frozen mix, min 8 per type ----
    bytype = collections.defaultdict(list)
    for x in ledger:
        bytype[x["perturbation"]["type"]].append(x["item_id"])
    types = sorted(bytype)
    tb = []
    for t in types:
        want = max(per_cell, round(n_tb * len(bytype[t]) / len(ledger)))
        pool = bytype[t][:]
        rng.shuffle(pool)
        tb += pool[:want]
    rng.shuffle(tb)
    tb = tb[:n_tb] if len(tb) > n_tb else tb

    # ---- eval_sweep: delta grid cells, >= per_cell each ----
    cells = collections.defaultdict(list)
    for x in ledger:
        if x["perturbation"]["type"] != "P-magnitude":
            continue
        d = x["perturbation"]["delta"]
        cells[(round(abs(d) * 100, 1), "pos" if d > 0 else "neg")].append(x["item_id"])
    sweep, cell_counts = [], {}
    for k in sorted(cells):
        pool = cells[k][:]
        rng.shuffle(pool)
        take = pool[:max(per_cell, n_sweep // max(len(cells), 1))]
        sweep += take
        cell_counts[f"{k[0]}%_{k[1]}"] = len(take)

    def strip(iid):
        it = dict(by_id[iid])
        for k in GOLD_KEYS:
            it.pop(k, None)
        return it

    for name, ids in (("eval_tb.jsonl", tb), ("eval_sweep.jsonl", sweep)):
        with (OUT / name).open("w", encoding="utf-8") as f:
            for i in ids:
                f.write(json.dumps(strip(i), ensure_ascii=False) + "\n")
        print(f"{name}: {len(ids)} items")

    strata = {"seed": SEED,
              "eval_tb": {"n": len(tb),
                          "by_type": dict(collections.Counter(
                              by_id[i]["perturbation"]["type"] for i in tb))},
              "eval_sweep": {"n": len(sweep), "by_delta_cell": cell_counts},
              "per_cell_floor": per_cell}
    (OUT / "strata.json").write_text(json.dumps(strata, ensure_ascii=False, indent=1),
                                     encoding="utf-8")

    # ---- the sealed snapshot filing_lookup serves (INV-9) ----
    snap = {x["item_id"]: x["filing_presented"] for x in ledger}
    (OUT / "filing_snapshot.json").write_text(json.dumps(snap, ensure_ascii=False),
                                              encoding="utf-8")
    (SYS / "filing_lookup_snapshot.py").write_text('''"""filing_lookup backed by the PERTURBED snapshot (INV-9).

The evaluation harness must never reach the live regulator API: a system could
diff its answer against reality and detect the perturbation. This module reads a
static file and has no network code at all.
"""
import json, pathlib
from dataclasses import dataclass

_SNAP = json.loads(pathlib.Path("data/benchmark/filing_snapshot.json").read_text(encoding="utf-8"))


@dataclass
class FiledValue:
    value: float | None
    unit: str
    scope: str
    consolidation: str
    period: str


def filing_lookup(item_id: str) -> FiledValue | None:
    """None means the metric is not filed -- NOT that its value is zero (INV-2)."""
    r = _SNAP.get(item_id)
    if r is None or r.get("value") is None:
        return None
    return FiledValue(r["value"], r["unit"], r["scope"], r["consolidation"], r["period"])
''', encoding="utf-8")

    # ---------------- Gate G-SEAL ----------------
    print("\n=== Gate G-SEAL ===")
    small_cells = {k: v for k, v in cell_counts.items() if v < per_cell}
    tb_small = {k: v for k, v in strata["eval_tb"]["by_type"].items() if v < per_cell}
    leak = set()
    for it in release:
        leak |= (GOLD_KEYS & set(it))
    for name in ("eval_tb.jsonl", "eval_sweep.jsonl"):
        for l in (OUT / name).open(encoding="utf-8"):
            leak |= (GOLD_KEYS & set(json.loads(l)))
    net = "requests" not in (SYS / "filing_lookup_snapshot.py").read_text(encoding="utf-8")

    checks = [
        ("每个扰动类型 >= 8 条", not tb_small, tb_small or "ok"),
        ("每个 δ 档位 >= 8 条", not small_cells, small_cells or f"{len(cell_counts)} cells"),
        ("发布集/评测集不含 gold 字段", not leak, leak or "clean"),
        ("filing_lookup 无网络代码", net, "static snapshot only"),
        ("ledger 与评测集分离", not (OUT / "eval_tb.jsonl").samefile(OUT / "ledger_sealed.jsonl"),
         "separate files"),
    ]
    for n, ok, d in checks:
        print(f"  [{'x' if ok else ' '}] {n:28} {d}")
    return all(ok for _, ok, _ in checks)


if __name__ == "__main__":
    ok = main()
    print("\nG-SEAL:", "PASS" if ok else "FAIL")
