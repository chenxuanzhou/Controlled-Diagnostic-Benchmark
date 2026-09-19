"""Recover C4 items lost to adjudicator token exhaustion."""
import json, pathlib, sys
sys.path.insert(0, "systems"); sys.path.insert(0, "scripts")
from score import parse
from run_agents import go

items = {json.loads(l)["item_id"]: json.loads(l)
         for l in open("data/benchmark/eval_tb.jsonl", encoding="utf-8")}
lost = []
for l in (pathlib.Path("out/runs") / "tb_c4.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    if "error" in r or not parse(r.get("content"))[0]:
        if r["item_id"] in items:
            lost.append(items[r["item_id"]])
print(f"C4 recoverable: {len(lost)}")
if lost:
    go(lost, "C4", "recover_c4.jsonl", workers=10, floor=16.0, chunk=20)
