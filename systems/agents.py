"""C3 (tool-augmented single agent) and C4 (multi-agent) for T-B.

The four tools are the point of P2. `filing_lookup` deliberately exposes
`scope`, `consolidation` and `period` alongside the value: the hypothesis is not
that the agent lacks the information, but that it does not use it. Handing the
scope fields over explicitly is what makes the failure interpretable.

INV-9: filing_lookup reads the sealed perturbed snapshot. No network, no live
regulator API -- otherwise a system could diff against reality and detect the
perturbation.
INV-5: rule 3 is the same frozen string as C0-C2.
"""
import json, pathlib, re, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pdfplumber
from prompts import RULE_3, METRIC_ZH, roc_to_gregorian

sys.path.insert(0, "scripts")
from pdf_rows import page_rows

SNAP = json.loads(pathlib.Path("data/benchmark/filing_snapshot.json").read_text(encoding="utf-8"))
PDF = pathlib.Path("data/corpus_full/raw_pdf")

UNIT_FACTORS = {   # to a canonical base per family
    "公噸": 1.0, "噸": 1.0, "tCO2e": 1.0, "kg": 1e-3, "公斤": 1e-3,
    "千公噸": 1e3, "百萬公升": 1.0, "公升": 1e-6, "ML": 1.0,
    "仟元": 1.0, "千元": 1.0, "萬元": 10.0, "億元": 1e5, "元": 1e-3,
    "%": 1.0, "人": 1.0, "件": 1.0,
}

TOOLS = [
    {"type": "function", "function": {
        "name": "pdf_table_extract",
        "description": "從報告書指定頁抽取以座標重建的表格列（含層級標籤前向填充）。",
        "parameters": {"type": "object", "properties": {
            "page": {"type": "integer", "description": "頁碼"},
            "keyword": {"type": "string", "description": "只回傳含此關鍵詞的列，可留空"}},
            "required": ["page"]}}},
    {"type": "function", "function": {
        "name": "filing_lookup",
        "description": ("查詢監管平台申報值。回傳 value/unit/scope/consolidation/period。"
                        "value 為 null 表示該指標未申報，不表示其值為零。"),
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "unit_normalize",
        "description": "單位換算。不支援的換算會回傳錯誤，不做靜默近似。",
        "parameters": {"type": "object", "properties": {
            "value": {"type": "number"}, "from_unit": {"type": "string"},
            "to_unit": {"type": "string"}}, "required": ["value", "from_unit", "to_unit"]}}},
    {"type": "function", "function": {
        "name": "calc",
        "description": "算術求值，例如 '(41683872-41020074)/41020074'。",
        "parameters": {"type": "object", "properties": {
            "expression": {"type": "string"}}, "required": ["expression"]}}},
]

SYSTEM_C3 = (
    "你是一名永續揭露稽核助理。使用提供的工具，判斷報告書的敘述與監管平台申報的指標是否一致。\n\n"
    "可用工具：pdf_table_extract, filing_lookup, unit_normalize, calc\n\n"
    "完成調查後，只輸出一行 JSON，不得有任何其他文字：\n"
    '{"verdict":"SUPPORTED|CONTRADICTED|NOT_COMPARABLE|NOT_APPLICABLE",'
    '"scope_check":{"aligned":true|false,"mismatch_type":null|"consolidation"|"scope"|'
    '"absolute_vs_intensity"|"indistinguishable_metric"}}\n\n'
    "規則：\n"
    "1. 比較任何兩個數值之前，必須先確認排放範疇、合併範圍與報告期間三者一致。"
    "任一不一致，verdict 必須為 NOT_COMPARABLE，並在 mismatch_type 說明是哪一項。\n"
    "2. filing_lookup 回傳 value 為 null 表示該指標未被申報，不表示其值為零 → NOT_APPLICABLE。\n"
    + RULE_3 + "\n"
    "4. 容差：單位歸一後相對誤差不超過 1% 視為一致。\n"
)


def _fmt_filed(item_id, metric_id, drop=()):
    r = SNAP.get(item_id)
    if r is None:
        return {"error": "not found"}
    out = {"metric": METRIC_ZH.get(metric_id, metric_id),
           "value": r.get("value"), "unit": r.get("unit"),
           "scope": r.get("scope"), "consolidation": r.get("consolidation"),
           "period": f"{roc_to_gregorian(r.get('period', 114))}年"}
    for k in drop:
        out.pop(k, None)
    return out


def run_tool(name, args, item, disabled=()):
    if name in disabled:
        return {"error": f"tool {name} is unavailable in this configuration"}
    try:
        if name == "filing_lookup":
            return _fmt_filed(item["item_id"], item["metric_id"])
        if name == "pdf_table_extract":
            pg = int(args.get("page", item["anchor"]["page"]))
            kw = (args.get("keyword") or "").strip()
            f = PDF / f"{item['company_id']}_2025.pdf"
            with pdfplumber.open(f) as pdf:
                if pg < 1 or pg > len(pdf.pages):
                    return {"error": "page out of range"}
                rows = page_rows(pdf.pages[pg - 1])
            out = [{"label": r["effective_label"][:40], "values": r["values"]}
                   for r in rows if r["values"]]
            if kw:
                out = [r for r in out if kw in r["label"]]
            return {"page": pg, "rows": out[:40]}
        if name == "unit_normalize":
            fu, tu = args.get("from_unit", ""), args.get("to_unit", "")
            if fu not in UNIT_FACTORS or tu not in UNIT_FACTORS:
                return {"error": f"unsupported conversion {fu} -> {tu}"}
            return {"value": float(args["value"]) * UNIT_FACTORS[fu] / UNIT_FACTORS[tu],
                    "unit": tu}
        if name == "calc":
            e = str(args.get("expression", ""))
            if not re.fullmatch(r"[0-9eE\.\+\-\*/\(\)\s,]+", e):
                return {"error": "expression contains disallowed characters"}
            return {"result": eval(e.replace(",", ""), {"__builtins__": {}}, {})}
    except Exception as ex:
        return {"error": f"{type(ex).__name__}: {ex}"[:120]}
    return {"error": "unknown tool"}


def run_c3(cl, model, item, evidence, disabled=(), max_turns=6, max_tokens=3000):
    """Tool-calling loop. Returns the harness result dict."""
    tools = [t for t in TOOLS if t["function"]["name"] not in disabled]
    msgs = [{"role": "system", "content": SYSTEM_C3},
            {"role": "user", "content":
             f"【永續報告書內容 第{item['anchor']['page']}頁】\n{evidence}\n\n"
             f"待稽核指標：{METRIC_ZH.get(item['metric_id'], item['metric_id'])}\n"
             f"請先用 filing_lookup 取得申報值，再判斷。"}]
    tin = tout = treason = ncalls = 0
    t0 = time.time()
    content = ""
    for _ in range(max_turns):
        r = cl.chat.completions.create(model=model, messages=msgs, tools=tools,
                                       max_tokens=max_tokens)
        m = r.choices[0].message
        us = r.usage
        tin += us.prompt_tokens; tout += us.completion_tokens
        treason += (us.completion_tokens_details.reasoning_tokens
                    if us.completion_tokens_details else 0)
        ncalls += 1
        if not getattr(m, "tool_calls", None):
            content = (m.content or "").strip()
            break
        msgs.append({"role": "assistant", "content": m.content or "",
                     "tool_calls": [tc.model_dump() for tc in m.tool_calls]})
        for tc in m.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            res = run_tool(tc.function.name, args, item, disabled)
            msgs.append({"role": "tool", "tool_call_id": tc.id,
                         "content": json.dumps(res, ensure_ascii=False)[:1800]})
    return {"item_id": item["item_id"], "model": model, "content": content,
            "prompt_tokens": tin, "completion_tokens": tout,
            "reasoning_tokens": treason, "api_calls": ncalls,
            "latency_s": round(time.time() - t0, 1), "ts": time.time()}


# ---------------- C4: four roles ----------------
ROLES = {
    "extractor": "你只負責抽取。從報告書內容中找出與指定指標相關的數值與其口徑描述，不做任何判斷。輸出簡短要點。",
    "retriever": "你只負責定位。呼叫 filing_lookup 取得申報值，原樣回報 value/unit/scope/consolidation/period，不下結論。",
    "auditor": ("你是對抗性稽核者。假定前面的證據是錯的，主動尋找口徑不匹配的可能性："
                "排放範疇、合併範圍、報告期間、絕對量與強度、以及是否可能指向另一個數值相近的指標。"
                "你必須提出至少一個反駁假設。"),
    "adjudicator": ("你綜合前三者做最終判定。只輸出一行 JSON：\n"
                    '{"verdict":"SUPPORTED|CONTRADICTED|NOT_COMPARABLE|NOT_APPLICABLE",'
                    '"scope_check":{"aligned":true|false,"mismatch_type":null|"consolidation"|'
                    '"scope"|"absolute_vs_intensity"|"indistinguishable_metric"}}\n'
                    "規則：口徑任一不一致 → NOT_COMPARABLE；申報值 null → NOT_APPLICABLE；"
                    + RULE_3 + " 容差 1%。"),
}


def run_c4(cl, model, item, evidence, max_tokens=1500, adjudicator_tokens=3200):
    tin = tout = treason = ncalls = 0
    t0 = time.time()
    notes = []
    metric = METRIC_ZH.get(item["metric_id"], item["metric_id"])
    base = (f"【報告書內容 第{item['anchor']['page']}頁】\n{evidence}\n\n待稽核指標：{metric}")

    for role in ("extractor", "retriever", "auditor", "adjudicator"):
        if role == "retriever":
            notes.append(("retriever", json.dumps(
                _fmt_filed(item["item_id"], item["metric_id"]), ensure_ascii=False)))
            continue
        ctx = base + "\n\n" + "\n".join(f"【{n}】{t}" for n, t in notes)
        # the adjudicator must emit JSON after reasoning; a 1500 cap leaves it
        # empty because reasoning consumes the whole budget (measured).
        mt = adjudicator_tokens if role == "adjudicator" else max_tokens
        r = cl.chat.completions.create(
            model=model, max_tokens=mt,
            messages=[{"role": "system", "content": ROLES[role]},
                      {"role": "user", "content": ctx}])
        us = r.usage
        tin += us.prompt_tokens; tout += us.completion_tokens
        treason += (us.completion_tokens_details.reasoning_tokens
                    if us.completion_tokens_details else 0)
        ncalls += 1
        notes.append((role, (r.choices[0].message.content or "").strip()[:900]))

    return {"item_id": item["item_id"], "model": model,
            "content": notes[-1][1], "prompt_tokens": tin,
            "completion_tokens": tout, "reasoning_tokens": treason,
            "api_calls": ncalls, "latency_s": round(time.time() - t0, 1),
            "ts": time.time()}
