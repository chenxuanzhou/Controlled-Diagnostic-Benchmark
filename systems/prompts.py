"""Prompt construction for T-B (spec v2 §附錄B, label space per TASK-06R).

INV-5: the NOT_COMPARABLE paragraph (rule 3) is one frozen string shared by every
condition C0-C4. Its sha256 goes into the run manifest for machine verification --
if the conditions do not quote it byte-identically, overclaim rate is not
comparable across them and Fig.3 is void.

ROC-era note: the filing stores 報告年度 as a Republic-of-China year ("114"). The
prompt renders it as the Gregorian year, because the provider's content filter
rejects the string "民國114年" outright -- measured, not assumed: "民國114年" is
blocked on all three Kimi models while "2025年" passes, with the report text and
every other field passing unchanged. This is a rendering change only; the stored
data is untouched.
"""
import hashlib

# ---- the frozen shared paragraph (INV-5) -------------------------------------
RULE_3 = (
    "3. 若無法定位到足以支持判斷的證據，輸出 NOT_COMPARABLE。"
    "錯誤的確定判斷比誠實的不確定嚴重得多。"
)

SYSTEM = (
    "你是一名永續揭露稽核助理。給定一段來自公司永續報告書的內容，"
    "以及該公司同年度向監管平台申報的一項結構化指標，判斷兩者是否一致。\n\n"
    "輸出以下 JSON，不得輸出任何其他內容：\n"
    "{\n"
    '  "verdict": "SUPPORTED" | "CONTRADICTED" | "NOT_COMPARABLE" | "NOT_APPLICABLE",\n'
    '  "value_claimed": {"value": number, "unit": string} | null,\n'
    '  "value_filed": {"value": number, "unit": string} | null,\n'
    '  "scope_check": {"aligned": true|false, "mismatch_type": null | "consolidation" | '
    '"scope" | "absolute_vs_intensity" | "indistinguishable_metric"},\n'
    '  "reasoning": string\n'
    "}\n\n"
    "規則：\n"
    "1. 比較任何兩個數值之前，必須先確認排放範疇、合併範圍與報告期間三者一致。"
    "任一不一致，verdict 必須為 NOT_COMPARABLE，並在 mismatch_type 說明是哪一項。\n"
    "2. 申報值為 null 表示該指標未被申報，不表示其值為零。此時 verdict 應為 NOT_APPLICABLE。\n"
    + RULE_3 + "\n"
    "4. 容差：單位歸一後相對誤差不超過 1% 視為一致。\n"
)

METRIC_ZH = {
    "ghg_scope1": "範疇一溫室氣體排放量", "ghg_scope2": "範疇二溫室氣體排放量",
    "ghg_scope3": "範疇三溫室氣體排放量", "ghg_intensity": "溫室氣體排放密集度",
    "renewable_share": "再生能源使用率", "water_use": "用水量",
    "water_intensity": "用水密集度", "waste_hazard": "有害廢棄物量",
    "waste_nonhazard": "非有害廢棄物量", "waste_total": "廢棄物總重量",
    "waste_intensity": "廢棄物密集度", "benefit_avg": "員工福利平均數",
    "salary_avg": "員工薪資平均數", "nonmgr_salary_avg": "非擔任主管全時員工薪資平均數",
    "nonmgr_salary_chg": "非擔任主管全時員工薪資平均數變動百分比",
    "salary_median": "非擔任主管全時員工薪資中位數",
    "salary_median_chg": "非擔任主管全時員工薪資中位數變動百分比",
    "female_mgr": "管理職女性主管佔比", "infosec_incidents": "資訊外洩事件數量",
    "infosec_pii_share": "個資相關外洩事件占比", "infosec_affected": "受影響顧客數",
    "injury_count": "職業災害人數", "injury_rate": "職業災害比率",
    "fire_count": "火災件數", "fire_casualties": "火災死傷人數",
    "fire_cas_share": "火災死傷人數占比",
}


def roc_to_gregorian(period) -> int:
    """報告年度 '114' -> 2025. Rendering only; the stored value is unchanged."""
    p = int(str(period))
    return p + 1911 if p < 1911 else p


def filing_block(fp, metric_id) -> str:
    name = METRIC_ZH.get(metric_id, metric_id)
    val = "null（未申報）" if fp.get("value") is None else f"{fp['value']}"
    cons = fp.get("consolidation") or "（未載明）"
    return ("【監管平台申報】\n"
            f"指標：{name}\n"
            f"申報值：{val}\n"
            f"單位：{fp.get('unit','')}\n"
            f"合併範圍／資料邊界：{cons}\n"
            f"報告年度：{roc_to_gregorian(fp.get('period', 114))}年")


def user_message(item, evidence: str) -> str:
    return (f"【永續報告書內容】\n{evidence}\n\n{filing_block(item['filing_presented'], item['metric_id'])}")


def prompt_hashes() -> dict:
    h = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
    return {"rule_3_sha256_16": h(RULE_3), "system_sha256_16": h(SYSTEM)}
