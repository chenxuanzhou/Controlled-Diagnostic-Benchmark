"""Diagnostic: re-run C4 on a few v2 items and KEEP the role notes (the production
runner stores only the adjudicator's final JSON). Output: out/runs/v2_c4_traces.jsonl

usage: python scripts/trace_c4_v2.py <item_id> [<item_id> ...]
"""
import json, pathlib, sys, time
sys.argv_backup = sys.argv[:]; ids = sys.argv[1:]; sys.argv = sys.argv[:1]
sys.path.insert(0, "systems"); sys.path.insert(0, "scripts")
import run_v2
import agents
from llm_client import client

items = {json.loads(l)["item_id"]: json.loads(l)
         for l in open("data/benchmark/v2_panel.jsonl", encoding="utf-8")}
cl = client(run_v2.BASE)
out = pathlib.Path("out/runs/v2_c4_traces.jsonl").open("a", encoding="utf-8")
for iid in ids:
    item = items[iid]
    ev = run_v2.evidence(item, "C0") + "\n\n" + run_v2.claim_block(item)
    notes = []
    base = f"【報告書內容 第{item['anchor']['page']}頁】\n{ev}\n\n待稽核指標：{agents.METRIC_ZH.get(item['metric_id'], item['metric_id'])}"
    for role in ("extractor", "retriever", "auditor", "adjudicator"):
        if role == "retriever":
            notes.append((role, json.dumps(agents._fmt_filed(item["item_id"], item["metric_id"]), ensure_ascii=False)))
            continue
        ctx = base + "\n\n" + "\n".join(f"【{n}】{t}" for n, t in notes)
        r = cl.chat.completions.create(model=run_v2.MODEL, max_tokens=6000 if role == "adjudicator" else 3000,
                                       messages=[{"role": "system", "content": agents.ROLES[role]},
                                                 {"role": "user", "content": ctx}])
        notes.append((role, (r.choices[0].message.content or "").strip()[:900]))
    out.write(json.dumps({"item_id": iid, "notes": notes, "ts": time.time()}, ensure_ascii=False) + "\n"); out.flush()
    print("==", iid)
    for n, t in notes:
        print(f"[{n}] {t[:500]}\n")
