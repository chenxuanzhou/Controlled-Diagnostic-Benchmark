"""TWSE ESG digital platform (esggenplus) API client.

Endpoints reverse-engineered from the SPA bundle on 2026-08-29.
Base: https://esggenplus.twse.com.tw/api/api
No auth / antiforgery token needed for the public inquiry endpoints.
"""
import json, time, pathlib, requests

BASE = "https://esggenplus.twse.com.tw/api/api"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
S = requests.Session()
S.headers.update({"User-Agent": UA, "Referer": "https://esggenplus.twse.com.tw/inquiry/report"})

MARKET = {"sii": 0, "otc": 1}          # 上市 / 上櫃


def industries(market=0):
    r = S.get(f"{BASE}/MopsSustainReport/industryAndCompanyCode",
              params={"marketType": market}, timeout=60)
    r.raise_for_status()
    return r.json()["data"]["industryNameList"]


def report_index(year, industry_names, market=0):
    """企業永續報告書申報清單 (S1 metadata). industry_names must be a LIST of names."""
    body = {"marketType": market, "year": year,
            "industryNameList": industry_names, "companyCodeList": []}
    r = S.post(f"{BASE}/MopsSustainReport/data", json=body, timeout=90)
    r.raise_for_status()
    j = r.json()
    return j["data"] if j.get("success") else []


def download_report(download_id, dest: pathlib.Path):
    """Fetch the filed sustainability-report PDF by its GUID."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with S.get(f"{BASE}/MopsSustainReport/data/FileStream",
               params={"id": download_id}, stream=True, timeout=600) as r:
        r.raise_for_status()
        ct = r.headers.get("Content-Type", "")
        if "pdf" not in ct:
            raise RuntimeError(f"not a pdf: {ct}")
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return dest.stat().st_size


def ghg_list(year, market=0):
    """溫室氣體排放及減量資訊 declarant list (S3). Returns declareId per company."""
    r = S.get(f"{BASE}/mopsGhg/list", params={"marketType": market, "year": year}, timeout=60)
    r.raise_for_status()
    return r.json()["data"]
