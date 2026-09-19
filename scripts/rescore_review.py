"""Review round 1 (2026-09-19): scoring that is a function of what the system is
SHOWN, plus the v2 label-substitution panel. Output: out/tables/review_r1.json.

v1 problem being corrected. P-scope, P-intensity, P-indistinct (and the value part
of P-crosscompany) replace only the filed VALUE; the presented record keeps the
original indicator label, unit and boundary. NOT_COMPARABLE is then not derivable
from the inputs. The `admissible` scoring below accepts every verdict the task's
own rules license for the record as presented:

  label unchanged, value within eps of the true filing  -> {SUPPORTED}
  label unchanged, value outside eps                     -> {CONTRADICTED, NOT_COMPARABLE}

Everything else keeps its single strict gold label. Strict scores are reported
next to admissible ones; nothing is dropped silently.
"""
import collections, json, math, pathlib, re, sys
sys.path.insert(0, "scripts")
from score import load_gold, parse, wilson
from authoritative import load, predictions, SOURCES
from scipy.stats import binomtest, fisher_exact

RUNS = pathlib.Path("out/runs")
B = pathlib.Path("data/benchmark")
EPS = 0.01
VALUE_ONLY = {"P-scope", "P-intensity", "P-indistinct", "P-crosscompany"}


def ledger():
    d = {}
    for l in (B / "ledger_sealed.jsonl").open(encoding="utf-8"):
        r = json.loads(l)
        d[r["item_id"]] = r
    return d


def admissible(L):
    t = L["perturbation"]["type"]
    g = L["gold"]["verdict"]
    if t not in VALUE_ONLY:
        return {g}
    pv, ov = L["filing_presented"]["value"], L["perturbation"]["original_value"]
    if t == "P-crosscompany":          # boundary text is also foreign -> NC stays admissible
        return {"CONTRADICTED", "NOT_COMPARABLE"}
    if ov and abs(pv - ov) / abs(ov) <= EPS:
        return {"SUPPORTED"}
    return {"CONTRADICTED", "NOT_COMPARABLE"}


def mcnemar(a_ok, b_ok):
    """exact McNemar on paired booleans: returns (a_only, b_only, p)."""
    a_only = sum(1 for x, y in zip(a_ok, b_ok) if x and not y)
    b_only = sum(1 for x, y in zip(a_ok, b_ok) if y and not x)
    n = a_only + b_only
    p = binomtest(a_only, n, 0.5).pvalue if n else 1.0
    return a_only, b_only, round(p, 4)


def acc(ids, ok):
    k = sum(ok[i] for i in ids); n = len(ids)
    return {"k": k, "n": n, "acc": round(k / n, 4) if n else None,
            "ci": [round(x, 3) for x in wilson(k, n)] if n else None}


SIB_KW = {
    "ghg_scope1": r"範疇一|範疇1|類別1|類別一|Scope ?1",
    "ghg_scope2": r"範疇二|範疇2|類別2|類別二|Scope ?2",
    "ghg_scope3": r"範疇三|範疇3|類別3|類別三|Scope ?3",
    "waste_hazard": r"(?<!非)有害",
    "waste_nonhazard": r"非有害|一般事業廢棄物|一般廢棄物",
    "waste_total": r"總量|總重|合計|總計",
}


def v1_part(L):
    gold = load_gold()
    raw = {name: load(f, c) for name, f, c in SOURCES}
    preds = {k: predictions(v) for k, v in raw.items()}
    core = ["C0", "C1", "C3", "C4"]
    paired = set.intersection(*(set(preds[c]) for c in core))
    types = sorted({L[i]["perturbation"]["type"] for i in paired})
    out = {"paired_n": len(paired)}

    # identical-to-control counts in the release and the evaluated set
    rel = collections.Counter(); ev = collections.Counter()
    in_tb = {json.loads(l)["item_id"] for l in (B / "eval_tb.jsonl").open(encoding="utf-8")}
    for i, r in L.items():
        t = r["perturbation"]["type"]
        if t in ("P-scope", "P-indistinct", "P-intensity"):
            pv, ov = r["filing_presented"]["value"], r["perturbation"]["original_value"]
            within = abs(pv - ov) / abs(ov) <= EPS
            rel[(t, "within_eps" if within else "outside")] += 1
            if i in in_tb:
                ev[(t, "within_eps" if within else "outside")] += 1
    # the public repository ships gold for the evaluated items only; the release-wide
    # counts (120/120 P-indistinct, 56/270 P-scope within eps) need the full ledger
    scope_key = "release" if len(L) >= 3000 else "ledger_rows_available"
    out["value_only_substitutions"] = {
        scope_key: {f"{t}|{k}": v for (t, k), v in sorted(rel.items())},
        "eval_tb": {f"{t}|{k}": v for (t, k), v in sorted(ev.items())}}

    tab = {}
    for c in core:
        strict = {i: preds[c][i][0] == L[i]["gold"]["verdict"] for i in preds[c]}
        adm = {i: preds[c][i][0] in admissible(L[i]) for i in preds[c]}
        row = {"strict_paired": acc(paired, strict), "admissible_paired": acc(paired, adm),
               "strict_full": acc(list(preds[c]), strict), "admissible_full": acc(list(preds[c]), adm),
               "by_type_paired": {}, "nc_rate_by_type_paired": {}, "supported_rate_by_type_paired": {}}
        for t in types:
            ids = [i for i in paired if L[i]["perturbation"]["type"] == t]
            row["by_type_paired"][t] = {"strict": acc(ids, strict), "admissible": acc(ids, adm)}
            row["nc_rate_by_type_paired"][t] = [sum(preds[c][i][0] == "NOT_COMPARABLE" for i in ids), len(ids)]
            row["supported_rate_by_type_paired"][t] = [sum(preds[c][i][0] == "SUPPORTED" for i in ids), len(ids)]
        # abstention on items whose admissible set excludes NC
        non_nc = [i for i in paired if "NOT_COMPARABLE" not in admissible(L[i])]
        row["nc_on_items_where_nc_inadmissible"] = [sum(preds[c][i][0] == "NOT_COMPARABLE" for i in non_nc), len(non_nc)]
        tab[c] = row
    out["conditions"] = tab

    # baselines on the paired panel
    const_nc_strict = sum(L[i]["gold"]["verdict"] == "NOT_COMPARABLE" for i in paired) / len(paired)
    const_nc_adm = sum("NOT_COMPARABLE" in admissible(L[i]) for i in paired) / len(paired)
    out["constant_NC_baseline_paired"] = {"strict": round(const_nc_strict, 4), "admissible": round(const_nc_adm, 4)}

    # paired tests (McNemar exact)
    tests = {}
    order = sorted(paired)
    for a, b in (("C1", "C3"), ("C1", "C4"), ("C3", "C4"), ("C0", "C1")):
        for name, fn in (("strict", lambda c, i: preds[c][i][0] == L[i]["gold"]["verdict"]),
                         ("admissible", lambda c, i: preds[c][i][0] in admissible(L[i]))):
            tests[f"{a}_vs_{b}|all|{name}"] = mcnemar([fn(a, i) for i in order], [fn(b, i) for i in order])
        for t in ("P-none", "P-scope"):
            ids = [i for i in order if L[i]["perturbation"]["type"] == t]
            tests[f"{a}_vs_{b}|{t}|strict"] = mcnemar(
                [preds[a][i][0] == L[i]["gold"]["verdict"] for i in ids],
                [preds[b][i][0] == L[i]["gold"]["verdict"] for i in ids])
    out["mcnemar"] = {k: {"a_only": v[0], "b_only": v[1], "p": v[2]} for k, v in tests.items()}

    # ablation
    abl = set.intersection(*(set(preds[c]) for c in ("C3", "C3-calc", "C3-filing_lookup")))
    o = sorted(abl)
    out["ablation"] = {"n": len(abl)}
    for c in ("C3", "C3-calc", "C3-filing_lookup"):
        out["ablation"][c] = {
            "strict": acc(o, {i: preds[c][i][0] == L[i]["gold"]["verdict"] for i in o}),
            "admissible": acc(o, {i: preds[c][i][0] in admissible(L[i]) for i in o}),
            "nc_outputs": sum(preds[c][i][0] == "NOT_COMPARABLE" for i in o)}
    out["ablation"]["constant_NC_strict"] = round(sum(L[i]["gold"]["verdict"] == "NOT_COMPARABLE" for i in o) / len(o), 4)
    for c in ("C3-calc", "C3-filing_lookup"):
        out["ablation"][f"mcnemar_C3_vs_{c}|strict"] = mcnemar(
            [preds["C3"][i][0] == L[i]["gold"]["verdict"] for i in o],
            [preds[c][i][0] == L[i]["gold"]["verdict"] for i in o])
        out["ablation"][f"mcnemar_C3_vs_{c}|admissible"] = mcnemar(
            [preds["C3"][i][0] in admissible(L[i]) for i in o],
            [preds[c][i][0] in admissible(L[i]) for i in o])

    # does the free-text reasoning name the substituted sibling? (C0/C1 only: they emit reasoning)
    named = {}
    text_rows = {}
    for fn_ in ("tb_text.jsonl", "recover_text.jsonl"):
        p = RUNS / fn_
        if p.exists():
            for l in p.open(encoding="utf-8"):
                r = json.loads(l)
                if r.get("content"):
                    text_rows[(r["item_id"], r.get("condition"))] = r["content"]
    filings = None
    from build_benchmark import load_filings, SCOPE_SIBLINGS
    filings = load_filings()
    for c in ("C0", "C1"):
        k = n = 0
        for i in preds[c]:
            r = L[i]
            if r["perturbation"]["type"] != "P-scope" or preds[c][i][0] != "CONTRADICTED":
                continue
            co, mid, pv = r["company_id"], r["metric_id"], r["filing_presented"]["value"]
            sib = [s for s in SCOPE_SIBLINGS.get(mid, []) if s in filings[co]
                   and math.isclose(filings[co][s]["value"], pv, rel_tol=1e-12)]
            txt = text_rows.get((i, c), "")
            m = re.search(r'"reasoning"\s*:\s*"(.*)', txt, re.S)
            reason = m.group(1) if m else txt
            n += 1
            if sib and re.search(SIB_KW[sib[0]], reason):
                k += 1
        named[c] = [k, n]
    out["p_scope_contradicted_reasoning_names_sibling"] = named
    return out, preds, paired


def v2_part():
    gp = B / "v2_ledger_sealed.jsonl"
    if not gp.exists():
        return None
    G = {}
    for l in gp.open(encoding="utf-8"):
        r = json.loads(l); G[r["item_id"]] = r
    P = {json.loads(l)["item_id"]: json.loads(l) for l in (B / "v2_panel.jsonl").open(encoding="utf-8")}
    out = {"n_items": len(G)}
    preds = {}
    for c in ("c1", "c3", "c4"):
        p = RUNS / f"v2_{c}.jsonl"
        if not p.exists():
            continue
        d = {}
        for l in p.open(encoding="utf-8"):
            r = json.loads(l)
            if "error" in r:
                continue
            v, mm = parse(r.get("content"))
            if v is not None:
                d[r["item_id"]] = (v, mm)
        preds[c.upper()] = d
    if not preds:
        return out
    common = set.intersection(*(set(d) for d in preds.values()))
    out["answered"] = {c: len(d) for c, d in preds.items()}
    out["paired_n"] = len(common)
    types = ["P-none", "P-scope", "P-indistinct", "P-intensity"]
    for c, d in preds.items():
        row = {}
        for scope_name, idset in (("own", set(d)), ("paired", common)):
            for t in types:
                ids = [i for i in idset if G[i]["perturbation"]["type"] == t]
                ok = {i: d[i][0] == G[i]["gold"]["verdict"] for i in ids}
                dist = collections.Counter(d[i][0] for i in ids)
                row[f"{scope_name}|{t}"] = dict(acc(ids, ok), dist=dict(dist))
                if t in ("P-scope", "P-indistinct"):
                    for tag, sel in (("identical_value", lambda i: G[i]["perturbation"]["rel_diff"] == 0),
                                     ("different_value", lambda i: G[i]["perturbation"]["rel_diff"] != 0)):
                        sub = [i for i in ids if sel(i)]
                        row[f"{scope_name}|{t}|{tag}"] = dict(acc(sub, ok),
                                                             dist=dict(collections.Counter(d[i][0] for i in sub)))
            nc = [i for i in idset if G[i]["gold"]["verdict"] == "NOT_COMPARABLE"]
            row[f"{scope_name}|all_substitutions"] = dict(
                acc(nc, {i: d[i][0] == "NOT_COMPARABLE" for i in nc}),
                affirmed=sum(d[i][0] == "SUPPORTED" for i in nc),
                mismatch_named=sum(d[i][0] == "NOT_COMPARABLE" and d[i][1] is not None for i in nc),
                mismatch_named_exact=sum(d[i][1] == G[i]["gold"]["mismatch_type"] for i in nc))
        out[c] = row
    # paired tests between conditions on the common items
    o = sorted(common)
    tests = {}
    cs = list(preds)
    for a in range(len(cs)):
        for b in range(a + 1, len(cs)):
            A, Bc = cs[a], cs[b]
            for t in types + ["ALL"]:
                ids = [i for i in o if t == "ALL" or G[i]["perturbation"]["type"] == t]
                tests[f"{A}_vs_{Bc}|{t}"] = mcnemar([preds[A][i][0] == G[i]["gold"]["verdict"] for i in ids],
                                                    [preds[Bc][i][0] == G[i]["gold"]["verdict"] for i in ids])
    out["mcnemar"] = {k: {"a_only": v[0], "b_only": v[1], "p": v[2]} for k, v in tests.items()}
    return out, preds, G, P


def v1_v2_same_items(L, v1preds, v2):
    """Same items, same condition (C1): value-only substitution (v1) vs record-level (v2)."""
    _, preds2, G, P = v2
    if "C1" not in preds2:
        return None
    res = {}
    for t in ("P-scope", "P-indistinct", "P-intensity", "P-none"):
        ids = [i for i in preds2["C1"] if G[i]["perturbation"]["type"] == t
               and P[i]["v1_item_id"] in v1preds["C1"]]
        v1 = collections.Counter(v1preds["C1"][P[i]["v1_item_id"]][0] for i in ids)
        v2c = collections.Counter(preds2["C1"][i][0] for i in ids)
        res[t] = {"n": len(ids), "v1_dist": dict(v1), "v2_dist": dict(v2c)}
        if t != "P-none":
            res[t]["mcnemar_NC"] = mcnemar([preds2["C1"][i][0] == "NOT_COMPARABLE" for i in ids],
                                           [v1preds["C1"][P[i]["v1_item_id"]][0] == "NOT_COMPARABLE" for i in ids])
    return res


def main():
    L = ledger()
    v1, v1preds, _ = v1_part(L)
    res = {"v1": v1}
    v2 = v2_part()
    if v2 and isinstance(v2, tuple):
        res["v2"] = v2[0]
        res["v1_vs_v2_C1_same_items"] = v1_v2_same_items(L, v1preds, v2)
    pathlib.Path("out/tables/review_r1.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1)[:6000])


if __name__ == "__main__":
    main()
