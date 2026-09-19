"""Tolerance sweep, rerun with the evidence the C1 condition is meant to see.

The original sweep (out/runs/sweep_c1.jsonl) ran C1 alone; harness.page_text
caches by (company, page) and ignores `limit`, so the anchor page was cut at 733
characters and the anchor figure was missing from the evidence of 30 of the 128
items. Here the anchor page is 2,200 characters (as in the main C1 run) and the
neighbours 733. Prompt, system message and items are otherwise identical to v1.
P-magnitude values are rounded to 10 significant digits so that no floating-point
tail (e.g. 1981.8745416000002) marks the record as tampered.

usage: python scripts/run_sweep_fixed.py [floor_cny]
"""
import concurrent.futures as cf, json, pathlib, sys, threading, time
sys.path.insert(0, "systems"); sys.path.insert(0, "scripts")
from llm_client import client
import harness
from harness import balance, OUT, SYSTEM
from prompts import filing_block
import pymupdf

MODEL = "kimi-k2.7-code"
BASE = "https://api.moonshot.cn/v1"
B = pathlib.Path("data/benchmark")
_lock = threading.Lock(); _pages = {}


def _page(co, pg, limit):
    if (co, pg) not in _pages:
        d = pymupdf.open(harness.PDF / f"{co}_2025.pdf")
        _pages[(co, pg)] = " ".join(d[pg - 1].get_text().split()) if 1 <= pg <= d.page_count else ""
        d.close()
    return _pages[(co, pg)][:limit]


def evidence(item):
    co, pg = item["company_id"], item["anchor"]["page"]
    parts = [_page(co, pg - 1, 733), _page(co, pg, 2200), _page(co, pg + 1, 733)]
    return "\n---\n".join(x for x in parts if x)


def call(cl, item):
    fp = dict(item["filing_presented"])
    if fp.get("value") is not None:
        fp["value"] = float(f"{fp['value']:.10g}")
    u = f"【永續報告書內容】\n{evidence(item)}\n\n{filing_block(fp, item['metric_id'])}"
    t0 = time.time()
    r = cl.chat.completions.create(
        model=MODEL, max_tokens=8000,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": u}])
    us = r.usage
    return {"item_id": item["item_id"], "condition": "C1", "model": MODEL,
            "content": (r.choices[0].message.content or "").strip(),
            "finish_reason": r.choices[0].finish_reason,
            "prompt_tokens": us.prompt_tokens, "completion_tokens": us.completion_tokens,
            "latency_s": round(time.time() - t0, 1), "ts": time.time()}


def _safe(cl, item, retries=3):
    for a in range(retries + 1):
        try:
            return call(cl, item)
        except Exception as e:
            if a == retries:
                return {"item_id": item["item_id"], "condition": "C1", "model": MODEL,
                        "error": type(e).__name__, "message": str(e)[:180], "ts": time.time()}
            time.sleep(2 * (a + 1))


def main(floor):
    items = [json.loads(l) for l in (B / "eval_sweep.jsonl").open(encoding="utf-8")]
    path = OUT / "sweep_c1_fixed.jsonl"
    ok = set()
    if path.exists():
        for l in path.open(encoding="utf-8"):
            d = json.loads(l)
            if d.get("content"):
                ok.add(d["item_id"])
    todo = [it for it in items if it["item_id"] not in ok]
    miss = sum(it["anchor"]["value_verbatim"] not in evidence(it) for it in items)
    print(f"{path.name}: {len(items)} items, {len(ok)} done, {len(todo)} to run; "
          f"anchor token absent from evidence: {miss}")
    if not todo:
        return
    cl = client(BASE); b0 = balance(); f = path.open("a", encoding="utf-8")
    for i in range(0, len(todo), 24):
        if balance() < floor:
            print("  !! STOP: below floor"); break
        with cf.ThreadPoolExecutor(max_workers=12) as ex:
            for fut in cf.as_completed([ex.submit(_safe, cl, it) for it in todo[i:i + 24]]):
                with _lock:
                    f.write(json.dumps(fut.result(), ensure_ascii=False) + "\n"); f.flush()
        print(f"  [{min(i + 24, len(todo))}/{len(todo)}] spent={b0 - balance():.3f} CNY", flush=True)
    f.close()


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 3.0)
