"""Evaluation harness: concurrent, resumable, cost-capped.

Three properties the budget forces:
  * concurrent  -- a single call takes 40-70s; 2,000 calls serially is a day
  * resumable   -- results append to jsonl keyed by (item, condition, model);
                   a rerun skips what is already there, so a crash costs nothing
  * cost-capped -- the account balance is polled between chunks and the run
                   aborts below the floor. Overspending is not recoverable.

INV-9: filings come from data/benchmark/filing_snapshot.json, never the live
regulator API. Only the LLM endpoint is contacted.
INV-5: every condition sends the identical frozen system prompt; its hash goes
into the manifest.
"""
import concurrent.futures as cf
import hashlib, json, pathlib, sys, threading, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import requests
import pymupdf
from llm_client import client, api_key
from prompts import SYSTEM, user_message, prompt_hashes

BASE = "https://api.moonshot.cn/v1"
PDF = pathlib.Path("data/corpus_full/raw_pdf")
OUT = pathlib.Path("out/runs"); OUT.mkdir(parents=True, exist_ok=True)
_lock = threading.Lock()
_page_cache = {}


def balance() -> float:
    r = requests.get(f"{BASE}/users/me/balance",
                     headers={"Authorization": f"Bearer {api_key()}"}, timeout=30)
    return r.json()["data"]["available_balance"]


def page_text(company, page, limit=2200):
    key = (company, page)
    if key not in _page_cache:
        f = PDF / f"{company}_2025.pdf"
        d = pymupdf.open(f)
        t = " ".join(d[page - 1].get_text().split()) if page <= d.page_count else ""
        d.close()
        _page_cache[key] = t[:limit]
    return _page_cache[key]


def evidence(item, condition, limit=2200):
    """C0 gives the anchor page only. C1 adds neighbouring pages (retrieval
    surrogate). C2/C3/C4 are built on top by their own runners."""
    co, pg = item["company_id"], item["anchor"]["page"]
    if condition == "C0":
        return page_text(co, pg, limit)
    if condition == "C1":
        parts = [page_text(co, p, limit // 3) for p in (pg - 1, pg, pg + 1) if p >= 1]
        return "\n---\n".join(x for x in parts if x)
    return page_text(co, pg, limit)


def one_call(cl, model, item, condition, max_tokens=4000):
    u = user_message(item, evidence(item, condition))
    t0 = time.time()
    r = cl.chat.completions.create(
        model=model, max_tokens=max_tokens,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": u}])
    us = r.usage
    rt = us.completion_tokens_details.reasoning_tokens if us.completion_tokens_details else 0
    return {"item_id": item["item_id"], "condition": condition, "model": model,
            "content": (r.choices[0].message.content or "").strip(),
            "finish_reason": r.choices[0].finish_reason,
            "prompt_tokens": us.prompt_tokens, "completion_tokens": us.completion_tokens,
            "reasoning_tokens": rt, "latency_s": round(time.time() - t0, 1),
            "ts": time.time()}


def run(tasks, out_name, workers=12, floor=15.0, chunk=24, max_tokens=4000, retries=3):
    """tasks: list of (item, condition, model). Returns the results path."""
    path = OUT / out_name
    done = set()
    if path.exists():
        for l in path.open(encoding="utf-8"):
            try:
                d = json.loads(l)
                done.add((d["item_id"], d["condition"], d["model"]))
            except Exception:
                pass
    todo = [t for t in tasks if (t[0]["item_id"], t[1], t[2]) not in done]
    print(f"{out_name}: {len(tasks)} tasks, {len(done)} already done, {len(todo)} to run")
    if not todo:
        return path

    cl = client(BASE)
    b_start = balance()
    print(f"  balance {b_start:.4f} CNY, floor {floor}")
    f = path.open("a", encoding="utf-8")
    n_ok = n_err = 0
    t_start = time.time()

    for i in range(0, len(todo), chunk):
        b = balance()
        if b < floor:
            print(f"  !! STOP: balance {b:.4f} below floor {floor}")
            break
        batch = todo[i:i + chunk]
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {}
            for t in batch:
                futs[ex.submit(_with_retry, cl, t, max_tokens, retries)] = t
            for fut in cf.as_completed(futs):
                res = fut.result()
                with _lock:
                    f.write(json.dumps(res, ensure_ascii=False) + "\n")
                    f.flush()
                n_ok += "error" not in res
                n_err += "error" in res
        el = time.time() - t_start
        spent = b_start - balance()
        n = i + len(batch)
        print(f"  [{n}/{len(todo)}] ok={n_ok} err={n_err} spent={spent:.4f} CNY "
              f"({spent/max(n,1):.5f}/call) {el/60:.1f}min "
              f"eta={(len(todo)-n)*el/max(n,1)/60:.0f}min", flush=True)
    f.close()
    print(f"  final balance {balance():.4f} CNY")
    return path


def _with_retry(cl, task, max_tokens, retries=3):
    item, cond, model = task
    for a in range(retries + 1):
        try:
            return one_call(cl, model, item, cond, max_tokens)
        except Exception as e:
            msg = str(e)
            # content_filter is mostly TRANSIENT on this endpoint: 3 of 4 pilot
            # rejections succeeded on a plain retry with the identical payload.
            # A small residual is persistent and is recorded as an error.
            if a == retries:
                return {"item_id": item["item_id"], "condition": cond, "model": model,
                        "error": type(e).__name__, "message": msg[:200], "ts": time.time()}
            time.sleep(2 * (a + 1))


def manifest(name, extra=None):
    m = {"prompt_hashes": prompt_hashes(), "base_url": BASE,
         "seed": 20260914, "ts": time.time()}
    m.update(extra or {})
    (OUT / f"{name}_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=1),
                                               encoding="utf-8")
    return m
