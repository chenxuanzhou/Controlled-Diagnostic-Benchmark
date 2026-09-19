"""Value-blind evidence sweep for items the locator left empty.

The locator, and any full-text search for the FILED value, can only find items
whose narrative figure already agrees. Items that disagree -- exactly the
CONTRADICTED and INSUFFICIENT ones -- are invisible to it. This sweep therefore
ranks purely on metric vocabulary and never looks at the filed value.
"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pdfplumber
from t3_yield import NUMTOK, UNIT_HINT, _sigdigits
from pdf_probe import rows_by_coords

VOCAB = {
 "ghg_scope1": ["範疇一", "直接排放", "直接溫室氣體"],
 "ghg_scope2": ["範疇二", "能源間接", "間接排放"],
 "ghg_scope3": ["範疇三", "其他間接", "價值鏈"],
 "ghg_intensity": ["排放密集度", "排放強度", "碳密集度"],
 "renewable_share": ["再生能源", "綠電", "綠色電力"],
 "water_use": ["取水量", "用水量", "總用水"],
 "water_intensity": ["用水密集度", "用水強度", "單位.{0,6}用水", "人均用水"],
 "waste_hazard": ["有害廢棄物", "有害事業廢棄物"],
 "waste_nonhazard": ["一般事業廢棄物", "非有害廢棄物"],
 "waste_total": ["廢棄物總量", "廢棄物產生量", "廢棄物清運"],
 "waste_intensity": ["廢棄物密集度", "人均廢棄物", "單位.{0,6}廢棄物"],
 "benefit_avg": ["員工福利", "福利費用"],
 "salary_avg": ["薪資平均", "平均薪資", "薪酬平均"],
 "nonmgr_salary_avg": ["非擔任主管", "非管理階層"],
 "nonmgr_salary_chg": ["非擔任主管", "非管理階層"],
 "salary_median": ["薪資中位", "中位數"],
 "salary_median_chg": ["薪資中位", "中位數"],
 "female_mgr": ["女性主管", "女性管理", "管理職女性"],
 "infosec_incidents": ["資訊外洩", "資料外洩", "資安事件"],
 "infosec_pii_share": ["個資", "個人資料"],
 "infosec_affected": ["受影響", "外洩"],
 "injury_count": ["職業災害", "職災"],
 "injury_rate": ["職業災害", "失能傷害", "傷害頻率", "FR", "SR"],
 "fire_count": ["火災", "火警", "消防"],
 "fire_casualties": ["火災", "火警"],
 "fire_cas_share": ["火災"],
}


def sweep(company, metric_ids, max_rows=3, width=140):
    import re
    pats = {m: [re.compile(v) for v in VOCAB.get(m, [m])] for m in metric_ids}
    found = {m: [] for m in metric_ids}
    with pdfplumber.open(f"data/raw_pdf/{company}_2025.pdf") as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            txt = page.extract_text() or ""
            live = [m for m in metric_ids if any(p.search(txt) for p in pats[m])]
            if not live:
                continue
            rows = [" ".join(" ".join(w["text"] for w in r).split())
                    for r in rows_by_coords(page)]
            for m in live:
                for line in rows:
                    if len(line) < 4 or not any(p.search(line) for p in pats[m]):
                        continue
                    nums = [t for t in NUMTOK.findall(line) if _sigdigits(t) >= 2]
                    if nums and UNIT_HINT.search(line):
                        found[m].append((pno, line[:width]))
    return {m: v[:max_rows] for m, v in found.items()}


if __name__ == "__main__":
    company = sys.argv[1]
    items = [json.loads(l) for l in open(_pick(company, "items"), encoding="utf-8")]
    todo = [i for i in items if i["company_id"] == company and not i["annotatable"]]
    res = sweep(company, [i["metric_id"] for i in todo])
    for it in todo:
        m = it["metric_id"]
        print(f"\n### {it['item_id']}  FILED {it['filed']['value']:,.4f} {it['filed']['unit']}")
        if not res[m]:
            print("    (value-blind sweep also finds nothing)")
        for pno, line in res[m]:
            print(f"    p{pno:<4} {line}")

# unit-pattern anchors: intensity metrics are frequently written as a unit
# ('kg CO2e / 噸膠結材料') with no 密集度/強度 wording at all -- measured on 1101 p31.
for _m, _ps in {
    'ghg_intensity': ['kg\\s*CO2e\\s*/', 'CO2e\\s*/\\s*(噸|公噸|每)', '每\\s*(噸|公噸|單位).{0,6}(排放|CO2)', '排放.{0,4}(強度|密集度)'],
    'water_intensity': ['(公噸|噸)\\s*水?\\s*/\\s*(公噸|噸|單位)', '每.{0,4}(噸|公噸|產品|人).{0,4}用水'],
    'waste_intensity': ['(公噸|噸)\\s*/\\s*(公噸|噸|單位)', '每.{0,4}(噸|公噸|產品|人).{0,4}廢棄'],
}.items():
    VOCAB[_m] = VOCAB.get(_m, []) + _ps
