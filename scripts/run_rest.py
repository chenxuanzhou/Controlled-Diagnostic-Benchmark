"""Remaining T-B runs: ablation arms, C4, and the Fig.6 tolerance sweep."""
import json, sys
sys.path.insert(0, "systems"); sys.path.insert(0, "scripts")
from run_agents import go
from harness import run, manifest, balance

items = [json.loads(l) for l in open("data/benchmark/eval_tb.jsonl", encoding="utf-8")]
sweep = [json.loads(l) for l in open("data/benchmark/eval_sweep.jsonl", encoding="utf-8")]

print("### Tab.5 ablation: C3 without filing_lookup")
go(items[:120], "C3", "tb_abl_lookup.jsonl", disabled=("filing_lookup",), floor=22.0)

print("\n### Tab.5 ablation: C3 without calc")
go(items[:120], "C3", "tb_abl_calc.jsonl", disabled=("calc",), floor=22.0)

print("\n### C4 multi-agent")
go(items[:120], "C4", "tb_c4.jsonl", workers=10, floor=22.0)

print("\n### Fig.6 tolerance sweep (C1)")
manifest("sweep", {"n_items": len(sweep), "model": "kimi-k2.7-code",
                   "conditions": ["C1"], "balance_before": balance()})
run([(it, "C1", "kimi-k2.7-code") for it in sweep], "sweep_c1.jsonl",
    workers=14, floor=20.0, chunk=32, max_tokens=4000)
