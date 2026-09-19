"""Score run results against the sealed ledger (gold = G-C).

The ledger is opened HERE and nowhere in systems/ -- the harness never sees gold
(INV-9). Scoring happens strictly after the calls are made.
"""
import collections, json, math, pathlib, re, sys

LEDGER = pathlib.Path("data/benchmark/ledger_sealed.jsonl")
LABELS = ["SUPPORTED", "CONTRADICTED", "NOT_COMPARABLE", "NOT_APPLICABLE"]
MISMATCH = ["consolidation", "scope", "absolute_vs_intensity",
            "indistinguishable_metric", "cross_company", None]


def load_gold():
    g = {}
    for l in LEDGER.open(encoding="utf-8"):
        d = json.loads(l)
        g[d["item_id"]] = {"verdict": d["gold"]["verdict"],
                           "mismatch_type": d["gold"]["mismatch_type"],
                           "ptype": d["perturbation"]["type"],
                           "delta": d["perturbation"].get("delta"),
                           "metric_id": d["metric_id"],
                           "industry": d.get("industry", "")}
    return g


def parse(content):
    """Pull the JSON object out of a response. Returns (verdict, mismatch_type)."""
    if not content:
        return None, None
    s = content.strip()
    s = re.sub(r"^```(?:json)?|```$", "", s, flags=re.M).strip()
    m = re.search(r"\{.*\}", s, flags=re.S)
    if not m:
        v = re.search(r"\b(SUPPORTED|CONTRADICTED|NOT_COMPARABLE|NOT_APPLICABLE)\b", s)
        return (v.group(1) if v else None), None
    try:
        d = json.loads(m.group(0))
    except Exception:
        v = re.search(r"\b(SUPPORTED|CONTRADICTED|NOT_COMPARABLE|NOT_APPLICABLE)\b", s)
        return (v.group(1) if v else None), None
    v = d.get("verdict")
    sc = d.get("scope_check") or {}
    return (v if v in LABELS else None), sc.get("mismatch_type")


def wilson(k, n, z=1.96):
    if not n:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    c = p + z * z / (2 * n)
    s = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - s) / den), min(1.0, (c + s) / den))


def score(path):
    gold = load_gold()
    rows = [json.loads(l) for l in pathlib.Path(path).open(encoding="utf-8")]
    cells = collections.defaultdict(list)
    for r in rows:
        cells[(r["model"], r["condition"])].append(r)

    out = {}
    for (model, cond), rs in sorted(cells.items()):
        n = len(rs)
        err = sum(1 for r in rs if "error" in r)
        empty = sum(1 for r in rs if "error" not in r and not r.get("content"))
        unparsed = correct = overclaim = 0
        n_scored = 0
        conf = collections.Counter()
        mm_conf = collections.Counter()
        by_ptype = collections.defaultdict(lambda: [0, 0])
        tol = collections.defaultdict(lambda: [0, 0])
        toks_in = toks_out = toks_reason = lat = 0
        for r in rs:
            if "error" in r:
                continue
            toks_in += r.get("prompt_tokens", 0)
            toks_out += r.get("completion_tokens", 0)
            toks_reason += r.get("reasoning_tokens", 0)
            lat += r.get("latency_s", 0)
            g = gold.get(r["item_id"])
            if not g:
                continue
            pred, mm = parse(r.get("content"))
            if pred is None:
                unparsed += 1
                continue
            n_scored += 1
            conf[(g["verdict"], pred)] += 1
            correct += pred == g["verdict"]
            if g["verdict"] == "NOT_COMPARABLE" and pred in ("SUPPORTED", "CONTRADICTED"):
                overclaim += 1
            by_ptype[g["ptype"]][1] += 1
            by_ptype[g["ptype"]][0] += pred == g["verdict"]
            if g["mismatch_type"]:
                mm_conf[(g["mismatch_type"], mm)] += 1
            if g["ptype"] == "P-magnitude" and g["delta"] is not None:
                key = round(abs(g["delta"]) * 100, 1)
                tol[key][1] += 1
                tol[key][0] += pred == "SUPPORTED"
        ok = n - err
        acc = correct / n_scored if n_scored else 0.0
        nc = sum(1 for r in rs if "error" not in r and
                 gold.get(r["item_id"], {}).get("verdict") == "NOT_COMPARABLE")
        out[f"{model}|{cond}"] = {
            "n": n, "errors": err, "empty_content": empty, "unparsed": unparsed,
            "n_scored": n_scored,
            "accuracy": round(acc, 4),
            "accuracy_wilson95": [round(x, 4) for x in wilson(correct, n_scored)],
            "overclaim_rate": round(overclaim / nc, 4) if nc else None,
            "by_perturbation": {k: {"acc": round(v[0] / v[1], 4), "n": v[1]}
                                for k, v in sorted(by_ptype.items())},
            "tolerance_curve": {str(k): {"supported_rate": round(v[0] / v[1], 4), "n": v[1]}
                                for k, v in sorted(tol.items())},
            "mismatch_confusion": {f"{a}->{b}": c for (a, b), c in sorted(
                mm_conf.items(), key=lambda x: -x[1])},
            "tokens": {"in_mean": round(toks_in / max(ok, 1)),
                       "out_mean": round(toks_out / max(ok, 1)),
                       "reasoning_share": round(toks_reason / max(toks_out, 1), 3)},
            "latency_s_mean": round(lat / max(ok, 1), 1),
        }
    return out


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "out/runs/pilot.jsonl"
    res = score(p)
    print(f"{'model|cond':28}{'n':>5}{'err':>5}{'空':>4}{'解析失败':>7}{'准确率':>9}{'overclaim':>11}{'in':>7}{'out':>7}{'秒':>6}")
    for k, v in res.items():
        oc = f"{v['overclaim_rate']:.3f}" if v["overclaim_rate"] is not None else "  -"
        print(f"{k:28}{v['n']:>5}{v['errors']:>5}{v['empty_content']:>4}{v['unparsed']:>7}"
              f"{v['accuracy']:>9.3f}{oc:>11}{v['tokens']['in_mean']:>7}"
              f"{v['tokens']['out_mean']:>7}{v['latency_s_mean']:>6.0f}")
    out = pathlib.Path(p).with_suffix(".scores.json")
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n-> {out}")
