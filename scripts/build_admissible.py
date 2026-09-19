"""Sidecar to the sealed ledger: the verdicts the task rules ADMIT for each of the
3,000 items, as a function of the record the system is shown (review round 1).

The ledger label says what was injected. For the value-level substitutions
(P-scope, P-intensity, P-indistinct, and the value part of P-crosscompany) the
presented record keeps the original indicator label, so the ledger label is not
derivable from the inputs. This file is what scoring should use.

Output: data/benchmark/admissible_r1.jsonl  (sealed side; never read by the harness)
"""
import collections, json, pathlib, sys
sys.path.insert(0, "scripts")
from rescore_review import ledger, admissible, EPS

L = ledger()
out = pathlib.Path("data/benchmark/admissible_r1.jsonl")
c = collections.Counter()
with out.open("w", encoding="utf-8") as f:
    for i, r in L.items():
        a = sorted(admissible(r))
        t = r["perturbation"]["type"]
        pv, ov = r["filing_presented"]["value"], r["perturbation"]["original_value"]
        within = (pv is not None and ov not in (None, 0) and abs(pv - ov) / abs(ov) <= EPS)
        f.write(json.dumps({"item_id": i, "type": t, "ledger_verdict": r["gold"]["verdict"],
                            "admissible_verdicts": a,
                            "presented_value_within_eps_of_true": bool(within),
                            "presented_identical_to_true": pv == ov}, ensure_ascii=False) + "\n")
        c[(t, "|".join(a))] += 1
for k, v in sorted(c.items()):
    print(f"{k[0]:16s} {k[1]:28s} {v}")
print("->", out)
