"""Score every run of the record-level substitution panel (v2).
Output: out/tables/v2_panel.json

Runs are discovered as out/runs/v2_<cond>[_<tag>].jsonl. The panel's gold is
data/benchmark/v2_ledger_sealed.jsonl; this script is the only reader of it.

Groups, by what the system is shown:
  control           true record, claim stated                                   -> SUPPORTED
  digits_differ     record declares another indicator; value differs by > eps   -> NOT_COMPARABLE
  digits_near       ... value within eps but not equal (hazardous waste != 0)   -> NOT_COMPARABLE
  digits_identical  ... value identical. All 29 are waste total vs non-hazardous
                    with hazardous waste zero or unfiled, so by the additivity
                    invariant the two indicators ARE the same quantity for that
                    company-year: SUPPORTED and NOT_COMPARABLE are both admissible.
                    "correct" below still counts NOT_COMPARABLE; read it as a
                    description of how the system resolves the case, not as accuracy.
"""
import collections, itertools, json, pathlib, re, sys
sys.path.insert(0, "scripts")
from score import parse, wilson
from scipy.stats import binomtest, fisher_exact

R = pathlib.Path("out/runs"); B = pathlib.Path("data/benchmark")
G = {}
for l in (B / "v2_ledger_sealed.jsonl").open(encoding="utf-8"):
    r = json.loads(l); G[r["item_id"]] = r


def group(i):
    p = G[i]["perturbation"]
    if p["type"] == "P-none":
        return "control"
    if p["rel_diff"] == 0:
        return "digits_identical"
    return "digits_near" if p["rel_diff"] <= 0.01 else "digits_differ"


def load(path):
    d = {}
    for l in path.open(encoding="utf-8"):
        r = json.loads(l)
        if "error" in r:
            continue
        v, mm = parse(r.get("content"))
        if v is not None:
            d[r["item_id"]] = (v, mm)
    return d


def rate(k, n):
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None,
            "ci": [round(x, 3) for x in wilson(k, n)] if n else None}


def mcnemar(a, b):
    ao = sum(1 for x, y in zip(a, b) if x and not y); bo = sum(1 for x, y in zip(a, b) if y and not x)
    return {"a_only": ao, "b_only": bo,
            "p": round(binomtest(ao, ao + bo, 0.5).pvalue, 4) if ao + bo else 1.0}


runs = {}
for p in sorted(R.glob("v2_*.jsonl")):
    name = p.stem[3:]
    if "truncated" in name or "traces" in name:
        continue
    runs[name] = load(p)

sizes = collections.Counter(group(i) for i in G)
out = {"panel": dict(sizes), "runs": {}}
for name, d in runs.items():
    row = {"answered": len(d)}
    for g in ("control", "digits_differ", "digits_near", "digits_identical"):
        ids = [i for i in d if group(i) == g]
        dist = collections.Counter(d[i][0] for i in ids)
        gold = "SUPPORTED" if g == "control" else "NOT_COMPARABLE"
        row[g] = {"correct": rate(dist[gold], len(ids)), "dist": dict(dist),
                  "correct_missing_as_wrong": rate(dist[gold], sizes[g])}
        if g != "control":
            row[g]["affirmed"] = rate(dist["SUPPORTED"], len(ids))
            row[g]["type_named_exact"] = sum(d[i][1] == G[i]["gold"]["mismatch_type"] for i in ids)
            row[g]["type_named_any"] = sum(d[i][0] == "NOT_COMPARABLE" and d[i][1] is not None for i in ids)
    # by ledger type
    for t in ("P-scope", "P-indistinct", "P-intensity"):
        ids = [i for i in d if G[i]["perturbation"]["type"] == t]
        row[t] = dict(collections.Counter(d[i][0] for i in ids))
    a = row["digits_differ"]["dist"]; b = row["digits_identical"]["dist"]
    tab = [[a.get("NOT_COMPARABLE", 0), sum(a.values()) - a.get("NOT_COMPARABLE", 0)],
           [b.get("NOT_COMPARABLE", 0), sum(b.values()) - b.get("NOT_COMPARABLE", 0)]]
    row["fisher_differ_vs_identical_p"] = float(f"{fisher_exact(tab)[1]:.3g}")
    out["runs"][name] = row

# paired contrasts between conditions of the main model
main = [c for c in ("c1", "c3", "c4") if c in runs]
common = set.intersection(*(set(runs[c]) for c in main)) if main else set()
out["paired_n"] = len(common)
out["paired"] = {}
for c in main:
    out["paired"][c] = {g: rate(sum(runs[c][i][0] == ("SUPPORTED" if g == "control" else "NOT_COMPARABLE")
                                    for i in common if group(i) == g),
                                sum(1 for i in common if group(i) == g))
                        for g in ("control", "digits_differ", "digits_identical")}
out["mcnemar"] = {}
o = sorted(common)
for a, b in itertools.combinations(main, 2):
    for g in ("control", "digits_differ", "digits_identical", "all"):
        ids = [i for i in o if g == "all" or group(i) == g]
        ok = lambda c: [runs[c][i][0] == ("SUPPORTED" if group(i) == "control" else "NOT_COMPARABLE") for i in ids]
        out["mcnemar"][f"{a}_vs_{b}|{g}"] = mcnemar(ok(a), ok(b))

# test-retest across C1 replicates of the main model
reps = [n for n in runs if re.fullmatch(r"c1(_r\d+)?", n)]
if len(reps) > 1:
    ids = sorted(set.intersection(*(set(runs[n]) for n in reps)))
    same = sum(len({runs[n][i][0] for n in reps}) == 1 for i in ids)
    out["replicates"] = {"runs": reps, "n_items_all_answered": len(ids),
                         "unanimous": same, "unanimous_rate": round(same / len(ids), 4),
                         "by_group": {g: [sum(len({runs[n][i][0] for n in reps}) == 1 for i in ids if group(i) == g),
                                          sum(1 for i in ids if group(i) == g)]
                                      for g in ("control", "digits_differ", "digits_identical")},
                         "pooled": {g: rate(sum(runs[n][i][0] == ("SUPPORTED" if g == "control" else "NOT_COMPARABLE")
                                                for n in reps for i in runs[n] if group(i) == g),
                                            sum(1 for n in reps for i in runs[n] if group(i) == g))
                                    for g in ("control", "digits_differ", "digits_identical")},
                         "pooled_affirmed_identical": rate(
                             sum(runs[n][i][0] == "SUPPORTED" for n in reps for i in runs[n] if group(i) == "digits_identical"),
                             sum(1 for n in reps for i in runs[n] if group(i) == "digits_identical"))}

# When the digits coincide, does an accepting response SAY why the two indicators
# coincide? Deterministic pattern over the free-text reasoning (text condition only):
# it states that hazardous waste is zero / absent, or that all waste is non-hazardous.
EQUIV = re.compile(r"無有害|未產生有害|沒有有害|未有有害|無產生有害|有害[^。；]{0,12}(為|皆為|均為)\s*(0|零)|"
                   r"(皆|均|全數|全部|都)(為|屬|是)?非有害|即(為|屬|等於|等同)非有害|等同非有害|"
                   r"即(為|屬)?(廢棄物)?總(量|重量)|全(部|數)為一般")
out["identical_digit_acceptances"] = {}
for name in runs:
    if not name.startswith("c1"):
        continue
    k = n = 0
    for l in (R / f"v2_{name}.jsonl").open(encoding="utf-8"):
        r = json.loads(l)
        i = r.get("item_id")
        if "error" in r or i not in runs[name] or group(i) != "digits_identical":
            continue
        if runs[name][i][0] != "SUPPORTED":
            continue
        m = re.search(r'"reasoning"\s*:\s*"(.*)', r.get("content") or "", re.S)
        n += 1
        k += bool(EQUIV.search(m.group(1) if m else ""))
    out["identical_digit_acceptances"][name] = {"states_why_indicators_coincide": k, "accepted": n}

pathlib.Path("out/tables/v2_panel.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
for name, row in out["runs"].items():
    print(f"{name:14s} answered {row['answered']:3d} | control {row['control']['correct']['k']}/{row['control']['correct']['n']}"
          f" | differ NC {row['digits_differ']['correct']['k']}/{row['digits_differ']['correct']['n']}"
          f" (affirmed {row['digits_differ']['affirmed']['k']})"
          f" | identical NC {row['digits_identical']['correct']['k']}/{row['digits_identical']['correct']['n']}"
          f" (affirmed {row['digits_identical']['affirmed']['k']}) | fisher p={row['fisher_differ_vs_identical_p']}")
print("paired n", out["paired_n"]); print(json.dumps(out.get("mcnemar"), indent=0)[:900])
print(json.dumps(out.get("replicates"), ensure_ascii=False))
