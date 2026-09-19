"""Reproduce every number in D0_REPORT.md section 4.

    python scripts/run_yield.py            # prints tables, writes out/yield/
"""
import json, pathlib, statistics, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from t3_yield import (scan, annotatable, filed_metrics, METRICS,
                      SCALES_WIDE, SCALES_LOOSE, SCALES_STRICT, CONSTRUCTION_TOL)

CASES = [("data/raw_pdf/1101_2025.pdf", "1101", "台泥"),
         ("data/raw_pdf/2002_2025.pdf", "2002", "中鋼"),
         ("data/raw_pdf/2882_2025.pdf", "2882", "國泰金")]

SETTINGS = [(0.02,  3, SCALES_WIDE,   "2%   / 3 sig / 9 scales  (widest)"),
            (0.02,  3, SCALES_LOOSE,  "2%   / 3 sig / 5 scales  (permissive)"),
            (0.005, 4, SCALES_STRICT, "0.5% / 4 sig / 3 scales  (default)"),
            (0.002, 4, SCALES_STRICT, "0.2% / 4 sig / 3 scales  (tightest)")]


def main():
    out = pathlib.Path("out/yield"); out.mkdir(parents=True, exist_ok=True)
    rec = {"tolerance_sweep": [], "per_metric_strict": {}, "annotatable": []}

    print("== 4.1  construction-tolerance sweep ==")
    print(f"{'setting':40s}{'hits':>10}{'rate':>8}{'per report':>12}")
    for tol, ms, sc, name in SETTINGS:
        tf = th = 0
        for pdf, code, _ in CASES:
            f, h = scan(pdf, code, tol=tol, min_sig=ms, scales=sc)
            tf += len(f); th += len(h)
        print(f"{name:40s}{th:>4}/{tf:<5}{th/tf*100:>7.0f}%{th/len(CASES):>12.1f}")
        rec["tolerance_sweep"].append(
            {"setting": name, "tol": tol, "min_sig": ms, "hits": th, "filed": tf,
             "rate": round(th/tf, 4), "per_report": round(th/len(CASES), 2)})

    print("\n== 4.1  per-metric hit rate at the default setting ==")
    pm = {}
    for pdf, code, lab in CASES:
        f, h = scan(pdf, code)
        for mid in f:
            pm.setdefault(mid, [0, 0])
            pm[mid][1] += 1
            pm[mid][0] += mid in h
    for mid, (hit, n) in sorted(pm.items(), key=lambda x: (-x[1][0]/x[1][1], x[0])):
        bar = "#" * hit + "." * (n - hit)
        print(f"   {mid:16s} {hit}/{n}  {bar}")
    rec["per_metric_strict"] = {k: {"hit": v[0], "n": v[1]} for k, v in pm.items()}

    print("\n== 4.4  annotatable items under the flipped unit (company, metric_id) ==")
    print(f"{'company':10s}{'filed':>8}{'annotatable':>13}{'coverage':>10}{'cand pages (med)':>18}")
    tf = ta = 0
    for pdf, code, lab in CASES:
        f, a = annotatable(pdf, code)
        tf += len(f); ta += len(a)
        med = statistics.median([len(v) for v in a.values()]) if a else 0
        print(f"{lab:10s}{len(f):>8}{len(a):>13}{len(a)/len(f)*100:>9.0f}%{med:>18.0f}")
        rec["annotatable"].append({"company": code, "label": lab, "filed": len(f),
                                   "annotatable": len(a), "median_candidate_pages": med})
    print(f"{'TOTAL':10s}{tf:>8}{ta:>13}{ta/tf*100:>9.0f}%")
    per = ta / len(CASES)
    print(f"\n   -> {per:.1f} annotatable T3 items per report")
    print(f"   -> 40 companies x 1 year = {per*40:.0f} candidates; T3 target 300 "
          f"=> {per*40/300*100:.0f}% of target")
    rec["summary"] = {"per_report": round(per, 2), "projected_40_companies": round(per*40),
                      "t3_target": 300, "coverage_pct": round(per*40/300*100)}

    (out / "yield.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwritten: {out/'yield.json'}")


if __name__ == "__main__":
    main()
