"""Run the v2 label-substitution panel (see build_v2_panel.py) under C1 / C3 / C4.

Differences from the v1 runners, all on the INPUT side and identical across
conditions:
  * the claim under audit is stated: indicator + verbatim narrative figure + page
  * the filing record carries the label, unit and boundary of the indicator whose
    value it holds (in v1 the label stayed that of the original indicator)
The frozen system prompts (INV-5) are byte-identical to v1. Token caps are raised
so that fewer calls die inside the reasoning budget (v1 lost 16% that way).

usage: python scripts/run_v2.py c1|c3|c4 [floor_cny] [--tag r2] [--model kimi-k3]
  --tag    writes to v2_<cond>_<tag>.jsonl: an independent replicate of the same panel
  --model  overrides the model (the tag is then mandatory)
"""
import concurrent.futures as cf, json, pathlib, sys, threading, time
sys.path.insert(0, "systems"); sys.path.insert(0, "scripts")
from llm_client import client
import harness
from harness import balance, OUT, SYSTEM
import pymupdf
import agents
from prompts import METRIC_ZH, roc_to_gregorian

MODEL = "kimi-k2.7-code"
BASE = "https://api.moonshot.cn/v1"
B = pathlib.Path("data/benchmark")
_lock = threading.Lock()

SNAP2 = json.loads((B / "v2_snapshot.json").read_text(encoding="utf-8"))
agents.SNAP.update(SNAP2)


def _fmt_filed_v2(item_id, metric_id, drop=()):
    r = agents.SNAP.get(item_id)
    if r is None:
        return {"error": "not found"}
    out = {"metric": METRIC_ZH.get(r.get("scope"), r.get("scope")),
           "value": r.get("value"), "unit": r.get("unit"),
           "scope": r.get("scope"), "consolidation": r.get("consolidation"),
           "period": f"{roc_to_gregorian(r.get('period', 114))}年"}
    for k in drop:
        out.pop(k, None)
    return out


agents._fmt_filed = _fmt_filed_v2


_pages = {}


def _page(co, pg, limit):
    """Own page reader. harness.page_text caches by (company, page) and ignores
    `limit`, so whichever condition touches a page first fixes its length for the
    whole process; run alone, C1 then sees a 733-character anchor page and the
    anchor can fall outside it (26 of these 95 items). Here the anchor page is
    always 2,200 characters, which contains every anchor span in the panel."""
    if (co, pg) not in _pages:
        d = pymupdf.open(harness.PDF / f"{co}_2025.pdf")
        _pages[(co, pg)] = " ".join(d[pg - 1].get_text().split()) if 1 <= pg <= d.page_count else ""
        d.close()
    return _pages[(co, pg)][:limit]


def evidence(item, condition):
    co, pg = item["company_id"], item["anchor"]["page"]
    if condition == "C1":
        parts = [_page(co, pg - 1, 733), _page(co, pg, 2200), _page(co, pg + 1, 733)]
        return "\n---\n".join(x for x in parts if x)
    return _page(co, pg, 2200)


def claim_block(item) -> str:
    c = item["claim"]
    return ("【待稽核宣稱】\n"
            f"報告書第{c['page']}頁所載「{METRIC_ZH.get(c['metric_id'], c['metric_id'])}」"
            f"：{c['value_verbatim']}")


def filing_block_v2(fp) -> str:
    val = "null（未申報）" if fp.get("value") is None else f"{fp['value']}"
    return ("【監管平台申報】\n"
            f"指標：{METRIC_ZH.get(fp['scope'], fp['scope'])}\n"
            f"申報值：{val}\n"
            f"單位：{fp.get('unit', '')}\n"
            f"合併範圍／資料邊界：{fp.get('consolidation') or '（未載明）'}\n"
            f"報告年度：{roc_to_gregorian(fp.get('period', 114))}年")


def call_c1(cl, item):
    u = (f"【永續報告書內容】\n{evidence(item, 'C1')}\n\n{claim_block(item)}\n\n"
         f"{filing_block_v2(item['filing_presented'])}")
    t0 = time.time()
    r = cl.chat.completions.create(
        model=MODEL, max_tokens=8000,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": u}])
    us = r.usage
    rt = us.completion_tokens_details.reasoning_tokens if us.completion_tokens_details else 0
    return {"item_id": item["item_id"], "model": MODEL,
            "content": (r.choices[0].message.content or "").strip(),
            "finish_reason": r.choices[0].finish_reason,
            "prompt_tokens": us.prompt_tokens, "completion_tokens": us.completion_tokens,
            "reasoning_tokens": rt, "latency_s": round(time.time() - t0, 1), "ts": time.time()}


def call_c3(cl, item):
    ev = evidence(item, "C0") + "\n\n" + claim_block(item)
    return agents.run_c3(cl, MODEL, item, ev, (), max_turns=6, max_tokens=6000)


def call_c4(cl, item):
    ev = evidence(item, "C0") + "\n\n" + claim_block(item)
    return agents.run_c4(cl, MODEL, item, ev, max_tokens=3000, adjudicator_tokens=6000)


def _safe(fn, cl, item, retries=3):
    for a in range(retries + 1):
        try:
            return fn(cl, item)
        except Exception as e:
            if a == retries:
                return {"item_id": item["item_id"], "model": MODEL,
                        "error": type(e).__name__, "message": str(e)[:180], "ts": time.time()}
            time.sleep(2 * (a + 1))


def go(kind, floor, tag=""):
    fn = {"c1": call_c1, "c3": call_c3, "c4": call_c4}[kind]
    items = [json.loads(l) for l in (B / "v2_panel.jsonl").open(encoding="utf-8")]
    path = OUT / (f"v2_{kind}_{tag}.jsonl" if tag else f"v2_{kind}.jsonl")
    ok = set()
    if path.exists():
        for l in path.open(encoding="utf-8"):
            d = json.loads(l)
            if d.get("content"):
                ok.add(d["item_id"])
    todo = [it for it in items if it["item_id"] not in ok]
    print(f"{path.name}: {len(items)} items, {len(ok)} with a verdict, {len(todo)} to run")
    if not todo:
        return
    cl = client(BASE); b0 = balance(); t0 = time.time()
    print(f"  balance {b0:.4f} CNY, floor {floor}")
    f = path.open("a", encoding="utf-8")
    for i in range(0, len(todo), 24):
        if balance() < floor:
            print(f"  !! STOP: below floor {floor}"); break
        batch = todo[i:i + 24]
        with cf.ThreadPoolExecutor(max_workers=12) as ex:
            futs = [ex.submit(_safe, fn, cl, it) for it in batch]
            for fut in cf.as_completed(futs):
                r = fut.result(); r["condition"] = kind.upper() + "-v2"
                with _lock:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n"); f.flush()
        n = i + len(batch)
        print(f"  [{n}/{len(todo)}] spent={b0 - balance():.3f} CNY {(time.time() - t0) / 60:.1f}min",
              flush=True)
    f.close()
    print(f"  final balance {balance():.4f} CNY")


if __name__ == "__main__":
    args = sys.argv[1:]
    tag = ""
    if "--tag" in args:
        i = args.index("--tag"); tag = args[i + 1]; del args[i:i + 2]
    if "--model" in args:
        i = args.index("--model"); MODEL = args[i + 1]; del args[i:i + 2]
        assert tag, "--model needs --tag so results never mix with the main run"
    go(args[0], float(args[1]) if len(args) > 1 else 3.0, tag)
