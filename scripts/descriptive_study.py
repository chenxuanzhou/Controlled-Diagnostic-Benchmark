"""The descriptive study, reported honestly (spec v2 §3, contribution #2).

A verbatim anchor requires the FILED value itself to satisfy C2 (>=4 significant
digits) and C3 (not a round number). Roughly 40% of (company, metric) pairs fail
that on the filing side alone -- an injury count of 34 or a fire count of 2 can
never be anchored, no matter how prominently the report states it.

So the unconditional rate confounds two very different things:
  * the company did not restate the figure
  * the figure is not precise enough for this method to trace

Both rates are reported. The conditional rate is the one that measures
disclosure behaviour; the unconditional rate is reported only for completeness,
and metrics with no anchorable pairs are marked NOT MEASURABLE rather than 0%.
"""
import collections, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from build_anchors import sig_digits, is_round

OUT = pathlib.Path("out/descriptive"); OUT.mkdir(parents=True, exist_ok=True)


def anchorable(v):
    """Can this filed value ever satisfy C2 + C3?"""
    return sig_digits(f"{v:.10g}") >= 4 and not is_round(v)


def main():
    pairs = [json.loads(l) for l in
             open("data/anchors/all_pairs.jsonl", encoding="utf-8")]
    by_m = collections.defaultdict(lambda: {"n": 0, "anchorable": 0, "anchored": 0})
    by_i = collections.defaultdict(lambda: {"n": 0, "anchorable": 0, "anchored": 0})
    for p in pairs:
        ok = anchorable(p["filed"]["value"])
        for d in (by_m[p["metric_id"]], by_i[p.get("industry", "")]):
            d["n"] += 1
            d["anchorable"] += ok
            d["anchored"] += p["verbatim_restated"]

    def rows(d):
        out = []
        for k, v in d.items():
            cond = v["anchored"] / v["anchorable"] if v["anchorable"] else None
            out.append({
                "key": k, "n_pairs": v["n"],
                "n_anchorable": v["anchorable"],
                "anchorable_share": round(v["anchorable"] / v["n"], 4),
                "n_anchored": v["anchored"],
                "conditional_restatement_rate": round(cond, 4) if cond is not None else None,
                "unconditional_restatement_rate": round(v["anchored"] / v["n"], 4),
                "measurable": v["anchorable"] > 0,
            })
        return sorted(out, key=lambda r: (r["conditional_restatement_rate"] is None,
                                          -(r["conditional_restatement_rate"] or 0)))

    tot = sum(v["n"] for v in by_m.values())
    anc_able = sum(v["anchorable"] for v in by_m.values())
    anc = sum(v["anchored"] for v in by_m.values())

    summary = {
        "scope": "all listed companies with a FY2025 sustainability report AND filed indicators",
        "n_companies": len({p["company_id"] for p in pairs}),
        "n_pairs": tot,
        "n_anchorable_pairs": anc_able,
        "anchorable_share": round(anc_able / tot, 4),
        "n_anchors": anc,
        "headline": {
            "conditional_verbatim_restatement_rate": round(anc / anc_able, 4),
            "conditional_verbatim_nonrestatement_rate": round(1 - anc / anc_able, 4),
            "denominator": "pairs whose FILED value satisfies C2 (>=4 sig digits) and C3 (non-round)",
        },
        "unconditional": {
            "verbatim_restatement_rate": round(anc / tot, 4),
            "verbatim_nonrestatement_rate": round(1 - anc / tot, 4),
            "why_not_the_headline": ("40% of pairs cannot produce an anchor because the filed "
                                     "value itself is too imprecise (an injury count of 34, a "
                                     "fire count of 2). Their 0% is a property of the anchor "
                                     "rule, not of disclosure."),
        },
        "caveats": [
            "VERBATIM only: a paraphrased or recomputed restatement counts as non-restated, "
            "so both rates are LOWER bounds on restatement (spec v2 §3).",
            "Metrics with zero anchorable pairs are NOT MEASURABLE by this method and must not "
            "be reported as 0% restatement.",
        ],
        "not_measurable_metrics": [r["key"] for r in rows(by_m) if not r["measurable"]],
        "by_industry": rows(by_i),
    }
    (OUT / "nonrestatement_rate.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "tab8_by_indicator.json").write_text(
        json.dumps(rows(by_m), ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"pairs {tot}   anchorable {anc_able} ({anc_able/tot*100:.1f}%)   anchors {anc}")
    print(f"HEADLINE conditional verbatim restatement = {anc/anc_able*100:.1f}%  "
          f"(non-restatement {100-anc/anc_able*100:.1f}%)")
    print(f"unconditional (reported for completeness) = {anc/tot*100:.1f}%")
    print(f"NOT MEASURABLE metrics: {summary['not_measurable_metrics']}")
    print(f"\n{'metric':22}{'pairs':>7}{'可锚定':>8}{'条件复述率':>12}")
    for r in rows(by_m):
        c = (f"{r['conditional_restatement_rate']*100:>11.1f}%"
             if r["conditional_restatement_rate"] is not None else "   NOT MEAS.")
        print(f"  {r['key']:20}{r['n_pairs']:>7}{r['n_anchorable']:>8}{c}")


if __name__ == "__main__":
    main()
