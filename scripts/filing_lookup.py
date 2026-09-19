"""S2/S3 structured-filing lookup, backed by TWSE OpenAPI.

Source: https://openapi.twse.com.tw/v1/opendata/t187ap46_L_{1..21}
        上市公司企業ESG資訊揭露彙總資料 (listed-company ESG disclosure summary)

The critical property for this benchmark: every emission figure ships with its
own 資料邊界 (data boundary / consolidation scope) and 取得驗證 (assurance) flag.
That is what makes scope-alignment machine-checkable rather than guesswork.

NOTE (verified 2026-08-29): the OpenAPI serves ONE reporting year only
(報告年度=114, i.e. FY2025). It is a snapshot, not a time series.
"""
import json, pathlib, requests
from dataclasses import dataclass, asdict

BASE = "https://openapi.twse.com.tw/v1/opendata"
CACHE = pathlib.Path("data/structured")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# topic tables that carry quantified indicators
TOPICS = {
    1: "溫室氣體排放", 2: "能源管理", 3: "水資源管理", 4: "廢棄物管理",
    5: "人力發展", 8: "氣候相關議題管理", 16: "資訊安全", 21: "職業安全衛生",
}

@dataclass
class FiledValue:
    value: float | None
    unit: str
    scope: str            # 範疇一 / 範疇二 / 範疇三 / intensity ...
    consolidation: str    # 資料邊界 -- parent-only vs consolidated
    period: str           # reporting year (ROC)
    assured: bool | None
    metric_id: str

    def __repr__(self):
        v = f"{self.value:,.1f}" if self.value is not None else "None"
        return (f"FiledValue({v} {self.unit} | scope={self.scope} | "
                f"consolidation={self.consolidation[:28]!r} | FY{self.period} | assured={self.assured})")


def _table(topic: int, refresh=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"t187ap46_L_{topic}.json"
    if refresh or not f.exists():
        r = requests.get(f"{BASE}/t187ap46_L_{topic}", headers={"User-Agent": UA}, timeout=120)
        r.raise_for_status()
        f.write_text(json.dumps(r.json(), ensure_ascii=False), encoding="utf-8")
    return json.loads(f.read_text(encoding="utf-8"))


def _num(x):
    try:
        s = str(x).replace(",", "").strip()
        return float(s) if s not in ("", "N/A", "-") else None
    except ValueError:
        return None


def filing_lookup(company_id: str, metric_id: str) -> FiledValue | None:
    """metric_id: 'ghg_scope1' | 'ghg_scope2' | 'ghg_scope3' | 'ghg_intensity'
                | 'renewable_share'

    Returns None when the company did not file the metric.
    None is NOT zero -- the caller must distinguish them (see plan §C.1).
    """
    if metric_id.startswith("ghg_"):
        rows = _table(1)
        rec = next((r for r in rows if r["公司代號"] == company_id), None)
        if rec is None:
            return None
        period = rec["報告年度"]
        if metric_id == "ghg_intensity":
            v = _num(rec["溫室氣體排放密集度(噸CO2e/單位)"])
            return None if v is None else FiledValue(
                v, "tCO2e/unit", "intensity", rec.get("範疇一資料邊界", ""), period, None, metric_id)
        n = {"ghg_scope1": "一", "ghg_scope2": "二", "ghg_scope3": "三"}[metric_id]
        v = _num(rec[f"範疇{n}排放量(噸CO2e)"])
        if v is None:
            return None
        return FiledValue(v, "tCO2e", f"範疇{n}", rec[f"範疇{n}資料邊界"], period,
                          rec[f"範疇{n}取得驗證"] == "是", metric_id)

    if metric_id == "renewable_share":
        rows = _table(2)
        rec = next((r for r in rows if r["公司代號"] == company_id), None)
        if rec is None:
            return None
        v = _num(str(rec["使用率(再生能源/總能源)"]).rstrip("%"))
        return None if v is None else FiledValue(
            v, "%", "renewable/total energy", rec.get("資料範圍", ""), rec["報告年度"],
            rec.get("取得驗證") == "是", metric_id)
    raise ValueError(f"unknown metric_id: {metric_id}")
