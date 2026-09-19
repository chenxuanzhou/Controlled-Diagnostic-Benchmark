"""T-B main matrix, text conditions (C0, C1) on the primary model."""
import json, sys
sys.path.insert(0, "systems")
from harness import run, manifest, balance

items = [json.loads(l) for l in open("data/benchmark/eval_tb.jsonl", encoding="utf-8")]
MODEL = "kimi-k2.7-code"
tasks = [(it, c, MODEL) for c in ("C0", "C1") for it in items]
manifest("tb_text", {"n_items": len(items), "model": MODEL,
                     "conditions": ["C0", "C1"], "balance_before": balance()})
run(tasks, "tb_text.jsonl", workers=14, floor=70.0, chunk=42, max_tokens=4000)
