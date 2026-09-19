"""Measure the T3 yield: for each FILED numeric metric, does the narrative report
state a matching figure -- and on which page?

This is the seed of the automatic gold-label constructor. A hit gives us, for free:
  * a T3 pair   (value_claimed, value_filed)
  * a T2 label  (the page the evidence sits on)

Deliberately conservative: a hit requires the number to match within tolerance AND
sit on a page whose text carries the metric's own vocabulary. Cross-unit scaling is
tried explicitly so that a report quoting kilotonnes still matches a filing in tonnes.
"""
import json, pathlib, re, statistics
import pymupdf

STRUCT = pathlib.Path("data/structured")
NUMTOK = re.compile(r'\d[\d,]*(?:\.\d+)?')

# metric_id -> (table, field, page-vocabulary)
METRICS = {
 # --- L_1 溫室氣體排放 ---
 "ghg_scope1":       (1, "範疇一排放量(噸CO2e)",                    ["範疇一", "直接溫室氣體", "直接排放"]),
 "ghg_scope2":       (1, "範疇二排放量(噸CO2e)",                    ["範疇二", "間接溫室氣體", "能源間接"]),
 "ghg_scope3":       (1, "範疇三排放量(噸CO2e)",                    ["範疇三", "其他間接"]),
 "ghg_intensity":    (1, "溫室氣體排放密集度(噸CO2e/單位)",            ["密集度", "排放強度"]),
 # --- L_2 能源管理 ---
 "renewable_share":  (2, "使用率(再生能源/總能源)",                   ["再生能源", "綠電", "可再生"]),
 # --- L_3 水資源管理 ---
 "water_use":        (3, "用水量(公噸)",                            ["用水量", "取水量", "自來水"]),
 "water_intensity":  (3, "用水密集度-密集度(公噸/單位) ",              ["用水密集度", "用水強度"]),
 # --- L_4 廢棄物管理 ---
 "waste_hazard":     (4, "有害廢棄物量-數據(公噸) ",                  ["有害廢棄物"]),
 "waste_nonhazard":  (4, "非有害廢棄物量-數據(公噸)",                 ["非有害廢棄物", "一般事業廢棄物"]),
 "waste_total":      (4, "總重量(有害+非有害)-數據(公噸)",             ["廢棄物", "廢棄物總量"]),
 "waste_intensity":  (4, "廢棄物密集度-密集度(公噸/單位) ",            ["廢棄物密集度", "廢棄物強度"]),
 # --- L_5 人力發展 ---
 "benefit_avg":      (5, "員工福利平均數(仟元/人)",                   ["員工福利", "福利費用"]),
 "salary_avg":       (5, "員工薪資平均數(仟元/人) ",                  ["員工薪資", "薪資平均"]),
 "nonmgr_salary_avg":(5, "非擔任主管職務之全時員工薪資平均數(仟元/人) ",  ["非擔任主管", "非主管"]),
 "nonmgr_salary_chg":(5, "非擔任主管職務之全時員工薪資平均數變動百分比",   ["非擔任主管", "非主管"]),
 "salary_median":    (5, "非擔任主管之全時員工薪資中位數(仟元/人) ",     ["薪資中位數", "員工薪資"]),
 "salary_median_chg":(5, "非擔任主管職務之全時員工薪資中位數變動百分比",   ["薪資中位數", "非主管"]),
 "female_mgr":       (5, "管理職女性主管佔比",                       ["女性主管", "管理職女性"]),
 # --- L_16 資訊安全 ---
 "infosec_incidents":(16, "資訊外洩事件數量",                        ["資訊外洩", "資安事件", "個資"]),
 "infosec_pii_share":(16, "與個資相關的資訊外洩事件占比",              ["個資", "資訊外洩"]),
 "infosec_affected": (16, "因資訊外洩事件而受影響的顧客數(人)",         ["受影響", "資訊外洩", "個資"]),
 # --- L_21 職業安全衛生 ---
 "injury_count":     (21, "職業災害人數及比率-人數",                  ["職業災害", "職災"]),
 "injury_rate":      (21, "職業災害人數及比率-比率",                  ["職業災害", "職災", "失能傷害"]),
 "fire_count":       (21, "火災件數(件)",                           ["火災"]),
 "fire_casualties":  (21, "火災死傷人數(人)",                       ["火災"]),
 "fire_cas_share":   (21, "火災死傷人數占員工總人數比率",              ["火災"]),
}
SCALES_WIDE   = [1, 1e-3, 1e3, 1e-2, 1e2, 1e-6, 1e6, 1e-4, 1e4]
SCALES_LOOSE  = [1, 1e-3, 1e3, 1e-2, 1e2]
SCALES_STRICT = [1, 1e-3, 1e3]
UNIT_HINT = re.compile(r"(公噸|噸|tCO2e|CO2e|仟元|千元|%|人|件|度|kWh|MWh|GJ)")

# Two tolerances, deliberately distinct (see D0_REPORT.md 4.2):
#   CONSTRUCTION_TOL -- locates candidate evidence. Must be tight, or coincidental
#                       matches enter the set (revenue 154,606,511 x0.01 lands within
#                       0.6% of Scope-2 emissions 1,536,737).
#   EVAL_EPSILON     -- decides the verdict. Using it for construction would be circular.
CONSTRUCTION_TOL = 0.005
EVAL_EPSILON     = 0.02


def _load(t):
    return json.loads((STRUCT / f"t187ap46_L_{t}.json").read_text(encoding="utf-8"))


def _num(x):
    s = str(x).replace(",", "").replace("%", "").strip()
    if s in ("", "N/A", "-", "None", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def filed_metrics(code):
    tables = {t: _load(t) for t in {m[0] for m in METRICS.values()}}
    out = {}
    for mid, (t, field, vocab) in METRICS.items():
        rec = next((r for r in tables[t] if r["公司代號"] == code), None)
        if rec is None:
            continue
        v = _num(rec.get(field))
        if v is not None and v != 0:
            out[mid] = v
    return out


def _sigdigits(tok):
    return len(tok.replace(",", "").lstrip("0").replace(".", "").rstrip("0"))


def scan(pdf_path, code, tol=CONSTRUCTION_TOL, min_sig=4, scales=None):
    """Locate, for each filed metric, a narrative figure that matches it.

    Pass tol=0.02, min_sig=3, scales=SCALES_LOOSE to reproduce the permissive
    setting whose false positives motivated the strict default.
    """
    scales = SCALES_STRICT if scales is None else scales
    filed = filed_metrics(code)
    doc = pymupdf.open(pdf_path)
    pages = [doc[i].get_text() for i in range(doc.page_count)]
    doc.close()
    hits = {}
    for mid, target in filed.items():
        _, _, vocab = METRICS[mid]
        found = None
        for pno, txt in enumerate(pages, 1):
            if not any(k in txt for k in vocab):
                continue
            for m in NUMTOK.finditer(txt):
                tok = m.group(0)
                if _sigdigits(tok) < min_sig:
                    continue
                v = float(tok.replace(",", ""))
                if v == 0:
                    continue
                if not UNIT_HINT.search(txt[max(0, m.start() - 40): m.end() + 40]):
                    continue
                for s in scales:
                    if abs(v * s - target) <= tol * abs(target):
                        found = (pno, tok, s, abs(v * s - target) / abs(target))
                        break
                if found:
                    break
            if found:
                break
        if found:
            hits[mid] = found
    return filed, hits


def annotatable(pdf_path, code, min_sig=3):
    """Which filed metrics have SOME quantified narrative statement to annotate?

    Value agreement is deliberately NOT required: a CONTRADICTED or INSUFFICIENT
    item is exactly one whose numbers do not agree. This is the candidate pool
    for the flipped annotation unit (company, metric_id) -- see D0_REPORT.md 4.4.
    """
    filed = filed_metrics(code)
    doc = pymupdf.open(pdf_path)
    pages = [doc[i].get_text() for i in range(doc.page_count)]
    doc.close()
    out = {}
    for mid in filed:
        _, _, vocab = METRICS[mid]
        cand = []
        for pno, txt in enumerate(pages, 1):
            if not any(k in txt for k in vocab):
                continue
            for m in NUMTOK.finditer(txt):
                if _sigdigits(m.group(0)) >= min_sig and                    UNIT_HINT.search(txt[max(0, m.start() - 40): m.end() + 40]):
                    cand.append(pno)
                    break
        if cand:
            out[mid] = cand
    return filed, out
