"""TASK-07R cost pilot: 20 items x 2 conditions x 2 models, instrumented.

Purpose is to replace every estimated number in config/model_matrix.json with a
measured one before committing the rest of the budget.
"""
import json, pathlib, sys
sys.path.insert(0, "systems"); sys.path.insert(0, "scripts")
from harness import run, manifest, balance

items = [json.loads(l) for l in
         open("data/benchmark/eval_tb.jsonl", encoding="utf-8")][:20]
MODELS = ["kimi-k2.7-code", "kimi-k3"]
CONDS = ["C0", "C1"]

tasks = [(it, c, m) for m in MODELS for c in CONDS for it in items]
manifest("pilot", {"n_items": len(items), "models": MODELS, "conditions": CONDS,
                   "balance_before": balance()})
run(tasks, "pilot.jsonl", workers=10, floor=90.0, chunk=20, max_tokens=4000)
