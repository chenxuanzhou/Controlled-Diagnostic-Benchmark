"""D3 corpus builder: assemble the matched (report PDF, structured filing) population.

Produces data/corpus_index.json -- one row per company-year that has BOTH a filed
sustainability-report PDF and filed structured ESG indicators, with the industry
stratum attached. This is the sampling frame for the benchmark.

Usage:
    python scripts/build_corpus.py --year 2025            # build index only
    python scripts/build_corpus.py --year 2025 --download --per-industry 5
"""
import argparse, json, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from twse_esg import industries, report_index, download_report
from filing_lookup import _table

# IFRS 永續揭露準則第一階段適用對象所在產業 + 高排放產業，優先分層
PRIORITY_STRATA = ["水泥工業", "鋼鐵工業", "半導體業", "金融保險業",
                   "化學工業", "食品工業", "紡織纖維", "航運業"]


def build(year: int):
    inds = [i["industryName"] for i in industries()]
    idx = report_index(year, inds)
    ghg = {r["公司代號"]: r for r in _table(1)}
    rows = []
    for r in idx:
        g = ghg.get(r["code"])
        if not g:
            continue
        s1 = str(g["範疇一排放量(噸CO2e)"]).strip()
        if s1 in ("", "0", "0.0000", "N/A"):
            continue
        rows.append({
            "company_code": r["code"],
            "company_name": r["name"],
            "short_name": r["shortName"],
            "industry": r["sector"],
            "fiscal_year": year,
            "reporting_interval": r["reportingInterval"],
            "assurance_provider": r["valiProvider"],
            "report_download_id": r["twFirstReportDownloadId"],
            "filed_year_roc": g["報告年度"],
            "filed_scope1": s1,
            "filed_scope1_boundary": g["範疇一資料邊界"],
            "filed_scope1_assured": g["範疇一取得驗證"],
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--per-industry", type=int, default=5)
    a = ap.parse_args()

    rows = build(a.year)
    out = pathlib.Path("data/corpus_index.json")
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"matched company-years: {len(rows)}  ->  {out}")

    by = {}
    for r in rows:
        by.setdefault(r["industry"], []).append(r)
    print(f"industries covered: {len(by)}")
    for s in PRIORITY_STRATA:
        print(f"  {s:10s} {len(by.get(s, []))}")

    if not a.download:
        return
    picks = [r for s in PRIORITY_STRATA for r in sorted(
        by.get(s, []), key=lambda x: x["company_code"])[:a.per_industry]]
    print(f"\ndownloading {len(picks)} reports...")
    for r in picks:
        dest = pathlib.Path(f"data/raw_pdf/{r['company_code']}_{a.year}.pdf")
        if dest.exists():
            print(f"  skip {dest.name}"); continue
        t = time.time()
        try:
            sz = download_report(r["report_download_id"], dest)
            print(f"  {dest.name}: {sz/1e6:.1f} MB  {time.time()-t:.0f}s")
        except Exception as e:
            print(f"  FAIL {r['company_code']}: {e}")


if __name__ == "__main__":
    main()
