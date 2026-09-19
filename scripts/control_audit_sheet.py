"""Audit sheet for unperturbed controls (P-none) that at least one condition rejected.

Writes out/tables/control_audit_sheet.md: for every such item, the filed record,
the anchor context from the page text, and each condition's verdict (+ the text
conditions' stated reason). The sheet is for a HUMAN reader; nothing here decides
whether the anchor is a genuine restatement.
"""
import collections, json, pathlib, re, sys
sys.path.insert(0, "scripts")
import pymupdf
from score import parse

B = pathlib.Path("data/benchmark"); R = pathlib.Path("out/runs")
PDF = pathlib.Path("data/corpus_full/raw_pdf")
L = {}
for l in (B / "ledger_sealed.jsonl").open(encoding="utf-8"):
    r = json.loads(l); L[r["item_id"]] = r

SRC = [("C0", "tb_text.jsonl", "C0"), ("C1", "tb_text.jsonl", "C1"),
       ("C3", "tb_c3.jsonl", None), ("C4", "tb_c4.jsonl", None)]
verd = collections.defaultdict(dict); why = collections.defaultdict(dict)
for name, fn, cond in SRC:
    for l in (R / fn).open(encoding="utf-8"):
        r = json.loads(l)
        if cond and r.get("condition") != cond:
            continue
        if "error" in r:
            continue
        v, _ = parse(r.get("content"))
        if v and L.get(r["item_id"], {}).get("perturbation", {}).get("type") == "P-none":
            verd[r["item_id"]][name] = v
            m = re.search(r'"reasoning"\s*:\s*"(.*?)"\s*}', r.get("content") or "", re.S)
            if m:
                why[r["item_id"]][name] = m.group(1).replace("\n", " ")[:420]

n_eval = len(verd)
flag = {i: v for i, v in verd.items() if any(x != "SUPPORTED" for x in v.values())}
lines = [f"# Control audit sheet\n\n{n_eval} evaluated P-none items; {len(flag)} rejected by at least one condition.\n"]
for i in sorted(flag):
    r = L[i]; a = r["anchor"]; co = r["company_id"]; fp = r["filing_presented"]
    d = pymupdf.open(PDF / f"{co}_2025.pdf")
    t = " ".join(d[a["page"] - 1].get_text().split()); d.close()
    s, e = a["span"]
    lines += [f"## {i}", f"- filed: **{fp['value']}** {fp['unit']} · boundary: {fp['consolidation'] or '(none)'}",
              f"- anchor p.{a['page']}: `{a['value_verbatim']}` (scale {a.get('scale', 1)})",
              f"- context: …{t[max(0, s - 160):e + 90]}…",
              f"- verdicts: {flag[i]}"]
    for c, w in why[i].items():
        if flag[i].get(c) != "SUPPORTED":
            lines.append(f"- {c} reason: {w}")
    lines.append("")
pathlib.Path("out/tables/control_audit_sheet.md").write_text("\n".join(lines), encoding="utf-8")
print(n_eval, "controls evaluated;", len(flag), "flagged")
print(collections.Counter(tuple(sorted(c for c, x in v.items() if x != "SUPPORTED")) for v in flag.values()))
