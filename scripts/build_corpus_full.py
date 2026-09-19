"""TASK-03R step 1-2: the full-market paired corpus.

Rolling selection on "has filed FY2025" -- never a fixed list, because filing is
still in progress and the roster moves.
"""
import argparse, json, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from twse_esg import industries, report_index, download_report
from t3_yield import filed_metrics, METRICS

OUT = pathlib.Path("data/corpus_full"); PDF = OUT / "raw_pdf"


def build_index():
    inds = [i["industryName"] for i in industries()]
    idx25 = {r["code"]: r for r in report_index(2025, inds)}
    idx24 = {r["code"]: r for r in report_index(2024, inds)}
    rows = []
    for code, r in idx25.items():
        fm = filed_metrics(code)
        if not fm:
            continue
        rows.append({
            "company_id": code, "name": r["name"], "short_name": r["shortName"],
            "industry": r["sector"], "fiscal_year": 2025,
            "reporting_interval": r["reportingInterval"],
            "n_filed_metrics": len(fm),
            "report_download_id_2025": r["twFirstReportDownloadId"],
            "report_download_id_2024": idx24.get(code, {}).get("twFirstReportDownloadId"),
            "fy2024_available": code in idx24,
        })
    rows.sort(key=lambda x: x["company_id"])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index-only", action="store_true")
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True); PDF.mkdir(exist_ok=True)
    f = OUT / "index.json"
    if f.exists():
        rows = json.loads(f.read_text(encoding="utf-8"))
        print(f"index reused: {len(rows)} paired company-years")
    else:
        rows = build_index()
        f.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"index built: {len(rows)} paired company-years -> {f}")
    print(f"  FY2024 report also available: {sum(1 for r in rows if r['fy2024_available'])}")
    print(f"  filed metrics per company: median "
          f"{sorted(r['n_filed_metrics'] for r in rows)[len(rows)//2]}")
    if a.index_only:
        return

    key = f"report_download_id_{a.year}"
    todo = [r for r in rows if r.get(key)]
    if a.limit:
        todo = todo[:a.limit]
    done = err = skip = 0
    t0 = time.time()
    for i, r in enumerate(todo, 1):
        dest = PDF / f"{r['company_id']}_{a.year}.pdf"
        if dest.exists() and dest.stat().st_size > 10000:
            skip += 1; continue
        try:
            download_report(r[key], dest); done += 1
        except Exception as e:
            err += 1
            print(f"  FAIL {r['company_id']}: {str(e)[:70]}", flush=True)
        if i % 25 == 0:
            el = time.time() - t0
            print(f"  [{i}/{len(todo)}] ok={done} skip={skip} err={err} "
                  f"{el/60:.1f}min eta={(len(todo)-i)*el/max(done,1)/60:.0f}min", flush=True)
    print(f"\nFY{a.year}: downloaded={done} skipped={skip} failed={err}")


if __name__ == "__main__":
    main()
