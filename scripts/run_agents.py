"""C3 / C4 / tool-ablation runs for T-B."""
import concurrent.futures as cf, json, pathlib, sys, threading, time
sys.path.insert(0, "systems"); sys.path.insert(0, "scripts")
from llm_client import client
from harness import evidence, balance, OUT
from agents import run_c3, run_c4

MODEL = "kimi-k2.7-code"
BASE = "https://api.moonshot.cn/v1"
_lock = threading.Lock()


def go(items, kind, out_name, disabled=(), workers=12, floor=18.0, chunk=24):
    path = OUT / out_name
    done = set()
    if path.exists():
        for l in path.open(encoding="utf-8"):
            try: done.add(json.loads(l)["item_id"])
            except Exception: pass
    todo = [it for it in items if it["item_id"] not in done]
    print(f"{out_name}: {len(items)} items, {len(done)} done, {len(todo)} to run "
          f"(disabled={disabled or 'none'})")
    if not todo: return
    cl = client(BASE); b0 = balance(); f = path.open("a", encoding="utf-8")
    print(f"  balance {b0:.4f}")
    t0 = time.time()
    for i in range(0, len(todo), chunk):
        if balance() < floor:
            print(f"  !! STOP below floor {floor}"); break
        batch = todo[i:i+chunk]
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {}
            for it in batch:
                if kind == "C3":
                    futs[ex.submit(_safe, run_c3, cl, MODEL, it, evidence(it, "C0"), disabled)] = it
                else:
                    futs[ex.submit(_safe, run_c4, cl, MODEL, it, evidence(it, "C0"))] = it
            for fut in cf.as_completed(futs):
                r = fut.result(); r["condition"] = kind + ("-" + "+".join(disabled) if disabled else "")
                with _lock:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n"); f.flush()
        n = i + len(batch); el = time.time() - t0
        print(f"  [{n}/{len(todo)}] spent={b0-balance():.3f} CNY {el/60:.1f}min "
              f"eta={(len(todo)-n)*el/max(n,1)/60:.0f}min", flush=True)
    f.close(); print(f"  final balance {balance():.4f}")


def _safe(fn, cl, model, item, ev, disabled=None):
    try:
        return fn(cl, model, item, ev, disabled) if disabled is not None else fn(cl, model, item, ev)
    except Exception as e:
        return {"item_id": item["item_id"], "model": model,
                "error": type(e).__name__, "message": str(e)[:180], "ts": time.time()}


if __name__ == "__main__":
    items = [json.loads(l) for l in open("data/benchmark/eval_tb.jsonl", encoding="utf-8")]
    what = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    if what == "c3":
        go(items[:n], "C3", "tb_c3.jsonl")
    elif what == "c4":
        go(items[:n], "C4", "tb_c4.jsonl", workers=10)
    elif what == "abl_lookup":
        go(items[:n], "C3", "tb_abl_lookup.jsonl", disabled=("filing_lookup",))
    elif what == "abl_calc":
        go(items[:n], "C3", "tb_abl_calc.jsonl", disabled=("calc",))
