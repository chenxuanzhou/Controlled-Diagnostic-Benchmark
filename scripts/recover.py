"""Re-run only the items whose response was empty or unparseable.

Those calls are billed in full (reasoning tokens are consumed either way) but
yield no datum, so recovering them is the cheapest way to raise n. A larger
max_tokens is the only change.
"""
import json, pathlib, sys
sys.path.insert(0, "systems"); sys.path.insert(0, "scripts")
from harness import run, balance, OUT
from score import parse

items = {json.loads(l)["item_id"]: json.loads(l)
         for l in open("data/benchmark/eval_tb.jsonl", encoding="utf-8")}
items.update({json.loads(l)["item_id"]: json.loads(l)
              for l in open("data/benchmark/eval_sweep.jsonl", encoding="utf-8")})

MODEL = "kimi-k2.7-code"
tasks = []
for fname, conds in [("tb_text.jsonl", ("C0", "C1")), ("sweep_c1.jsonl", ("C1",))]:
    p = OUT / fname
    if not p.exists():
        continue
    for l in p.open(encoding="utf-8"):
        r = json.loads(l)
        if "error" in r:
            continue
        v, _ = parse(r.get("content"))
        if v is None and r["item_id"] in items:
            tasks.append((items[r["item_id"]], r["condition"], MODEL))
print(f"recoverable text-condition items: {len(tasks)}")
if tasks:
    run(tasks, "recover_text.jsonl", workers=14, floor=20.0, chunk=32, max_tokens=8000)
