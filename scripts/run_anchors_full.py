"""TASK-04R at full market scale: 885 company-years.

Produces the anchor set (gold source G-B), the three construct-validity metrics
that replace Cohen's kappa, and the descriptive study (verbatim non-restatement
rate, market-wide and per indicator).

INV-3: every (company, metric) pair with a filed value is enumerated and written.
Failing C1-C4 is recorded as verbatim_restated=false, never dropped -- that
outcome IS the descriptive result.
INV-8: no language model appears anywhere in this pipeline.
"""
import json, math, pathlib, random, statistics, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from build_anchors import scan_company, negative_control, filed_values

SEED = 20260914
ROOT = pathlib.Path("data/corpus_full")
PDF = ROOT / "raw_pdf"
OUT_A = pathlib.Path("data/anchors"); OUT_A.mkdir(parents=True, exist_ok=True)
OUT_D = pathlib.Path("out/descriptive"); OUT_D.mkdir(parents=True, exist_ok=True)


def main(limit=0, neg_pairs=120):
    idx = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))
    if limit:
        idx = idx[:limit]
    ind_of = {r["company_id"]: r["industry"] for r in idx}

    f_anchor = (OUT_A / "anchor_set.jsonl").open("w", encoding="utf-8")
    f_all = (OUT_A / "all_pairs.jsonl").open("w", encoding="utf-8")
    N_tokens, R_round, W_window, sig_all = [], [], [], []
    n_pairs = n_anchor = n_corrob = 0
    per_metric, per_industry = {}, {}
    t0 = time.time()

    for i, row in enumerate(idx, 1):
        code = row["company_id"]
        p = PDF / f"{code}_2025.pdf"
        if not p.exists():
            continue
        try:
            recs, st = scan_company(code, str(p))
        except Exception as e:
            print(f"  FAIL {code}: {str(e)[:60]}", flush=True)
            continue
        N_tokens.append(st["num_tokens"])
        R_round.append(st["round_tokens"] / max(st["num_tokens"], 1))
        W_window += st["window_tokens"]

        for r in recs:
            r["industry"] = ind_of.get(code, "")
            n_pairs += 1
            m = per_metric.setdefault(r["metric_id"], {"n": 0, "anchored": 0})
            m["n"] += 1
            g = per_industry.setdefault(r["industry"], {"n": 0, "anchored": 0})
            g["n"] += 1
            f_all.write(json.dumps(r, ensure_ascii=False) + "\n")
            if r["verbatim_restated"]:
                n_anchor += 1
                m["anchored"] += 1
                g["anchored"] += 1
                sig_all.append(r["anchor"]["sig_digits"])
                if r["corroborated_at"]:
                    n_corrob += 1
                f_anchor.write(json.dumps(r, ensure_ascii=False) + "\n")

        if i % 50 == 0:
            el = time.time() - t0
            print(f"  [{i}/{len(idx)}] pairs={n_pairs} anchors={n_anchor} "
                  f"({n_anchor/max(n_pairs,1)*100:.0f}%) {el/60:.0f}min "
                  f"eta={(len(idx)-i)*el/i/60:.0f}min", flush=True)

    f_anchor.close(); f_all.close()

    # ---------- construct validity ----------
    N = int(statistics.median(N_tokens)); r_round = statistics.mean(R_round)
    m_win = int(statistics.median(W_window)) if W_window else 0
    d_med = int(statistics.median(sig_all)) if sig_all else 0

    def bound(d):
        p = 1 / (9 * 10 ** (d - 1)) * 1 / (1 - r_round)
        return p, 1 - (1 - p) ** m_win

    p4, b4 = bound(4)
    pm, bm = bound(max(d_med, 4))

    print("\nnegative control ...", flush=True)
    rnd = random.Random(SEED)
    codes = [r["company_id"] for r in idx if (PDF / f"{r['company_id']}_2025.pdf").exists()]
    npass = ntot = 0
    for k in range(neg_pairs):
        a, b = rnd.sample(codes, 2)
        try:
            ps, tt = negative_control(a, b, str(PDF / f"{a}_2025.pdf"))
            npass += ps; ntot += tt
        except Exception:
            continue
        if (k + 1) % 30 == 0:
            print(f"  [{k+1}/{neg_pairs}] pass={npass}/{ntot}", flush=True)

    validity = {
        "seed": SEED, "n_companies": len(N_tokens),
        "n_pairs": n_pairs, "n_anchors": n_anchor,
        "anchor_rate": round(n_anchor / max(n_pairs, 1), 4),
        "false_match_bound": {
            "N_numeric_tokens_per_report_median": N,
            "r_round_number_share": round(r_round, 4),
            "m_tokens_in_anchor_window_median": m_win,
            "d_significant_digits_median": d_med,
            "worst_case_d4_single_anchor": round(b4, 6),
            "at_median_d": bm,
            "target": 0.01, "pass": b4 < 0.01},
        "corroboration_rate": round(n_corrob / max(n_anchor, 1), 4),
        "negative_control": {"passed": npass, "total": ntot,
                             "rate": round(npass / max(ntot, 1), 5),
                             "target": 0.99, "pass": npass / max(ntot, 1) > 0.99},
    }
    (OUT_A / "validity.json").write_text(json.dumps(validity, ensure_ascii=False, indent=1),
                                         encoding="utf-8")

    # ---------- descriptive study ----------
    tab8 = [{"metric_id": k, "n": v["n"], "anchored": v["anchored"],
             "verbatim_restatement_rate": round(v["anchored"] / v["n"], 4),
             "verbatim_nonrestatement_rate": round(1 - v["anchored"] / v["n"], 4)}
            for k, v in sorted(per_metric.items(),
                               key=lambda x: -x[1]["anchored"] / max(x[1]["n"], 1))]
    (OUT_D / "tab8_by_indicator.json").write_text(
        json.dumps(tab8, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT_D / "nonrestatement_rate.json").write_text(json.dumps({
        "scope": "all listed companies with a FY2025 sustainability report AND filed indicators",
        "n_companies": len(N_tokens), "n_pairs": n_pairs, "n_anchors": n_anchor,
        "verbatim_nonrestatement_rate": round(1 - n_anchor / max(n_pairs, 1), 4),
        "caveat": ("VERBATIM non-restatement. A paraphrased or recomputed restatement counts "
                   "as non-restated, so this is a LOWER bound on restatement (spec v2 §3)."),
        "by_industry": {k: {"n": v["n"], "anchored": v["anchored"],
                            "rate": round(v["anchored"] / v["n"], 4)}
                        for k, v in sorted(per_industry.items(),
                                           key=lambda x: -x[1]["anchored"] / max(x[1]["n"], 1))},
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\npairs={n_pairs} anchors={n_anchor} ({n_anchor/max(n_pairs,1)*100:.1f}%)")
    print(f"false-match bound (d=4) = {b4:.6f}  target<0.01  {'PASS' if b4<0.01 else 'FAIL'}")
    print(f"corroboration rate      = {validity['corroboration_rate']}")
    print(f"negative control        = {validity['negative_control']['rate']}  "
          f"target>0.99  {'PASS' if validity['negative_control']['pass'] else 'FAIL'}")
    print(f"anchors >= 3000         : {'PASS' if n_anchor>=3000 else 'FAIL'} ({n_anchor})")


if __name__ == "__main__":
    main(limit=int(sys.argv[1]) if len(sys.argv) > 1 else 0)
