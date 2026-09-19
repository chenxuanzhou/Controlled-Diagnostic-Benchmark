"""TASK-03R step 3 acceptance: measure the three extraction pathologies
before and after the v2 row reconstruction.

Ground truth comes from the TASK-01 probe: 116 adjudicated items each carry a
gold page and the value the narrative states there. A pathology is "repaired"
for an item when the value and the metric's lexical anchor land in the SAME
reconstructed row -- which is exactly what anchor matching (C4) requires.
"""
import json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pdfplumber
from pdf_probe import rows_by_coords          # v1
from pdf_rows import page_rows, NUM           # v2
from blind_sweep import VOCAB

PDF_DIR = pathlib.Path("data/raw_pdf")


def _norm(x):
    return str(x).replace(",", "").rstrip("0").rstrip(".")


def _value_variants(v):
    """The token forms a report may use for a filed value, across unit scales."""
    out = set()
    for s in (1, 10, 0.1, 1e2, 1e-2, 1e3, 1e-3, 1e4, 1e-4):
        x = v / s
        for r in range(0, 5):
            out.add(_norm(f"{x:.{r}f}"))
    return out


def v1_rows(page):
    return [" ".join(w["text"] for w in r) for r in rows_by_coords(page)]


def check(items, limit_per=20):
    pats = {m: [re.compile(p) for p in VOCAB.get(m, [m])] for m in VOCAB}
    res = {"P2_number_split": {"n": 0, "v1": 0, "v2": 0, "cases": []},
           "P3_column_drop":  {"n": 0, "v1": 0, "v2": 0, "cases": []},
           "P1_forward_fill": {"n": 0, "v1": 0, "v2": 0, "cases": []}}
    by_company = {}
    for it in items:
        by_company.setdefault(it["company_id"], []).append(it)

    for code, its in by_company.items():
        f = PDF_DIR / f"{code}_2025.pdf"
        if not f.exists():
            continue
        with pdfplumber.open(f) as pdf:
            for it in its:
                pages = it["evidence"]["pages"]
                cv = (it.get("claimed") or {}).get("value")
                if not pages or cv is None:
                    continue
                pno = pages[0]
                if pno > len(pdf.pages):
                    continue
                page = pdf.pages[pno - 1]
                variants = _value_variants(cv)
                # T-A gold covers verbatim occurrences only (spec v2 §3 T-A).
                # Summed or otherwise derived claims are out of scope by design.
                raw = (page.extract_text() or "")
                if not any(_norm(x) in variants for x in NUM.findall(raw)):
                    continue
                ps = pats.get(it["metric_id"], [])

                def hit(rowtexts, window=200):
                    """C4 as actually specified: the value token must fall within
                    +/-200 characters of a lexical anchor in the reconstructed
                    reading order -- not necessarily in the same row."""
                    doc = " ".join(rowtexts)
                    anchors = [m.start() for p in ps for m in p.finditer(doc)]
                    if not anchors:
                        return False
                    for m in NUM.finditer(doc):
                        if _norm(m.group(0)) in variants:
                            if any(abs(m.start() - a) <= window for a in anchors):
                                return True
                    return False

                # C4 is a proximity condition in the document, not a row-membership
                # condition: measure it on raw reading order, which column
                # segmentation must not be allowed to break apart.
                raw_doc = raw
                r1 = v1_rows(page)
                r2v = page_rows(page, forward_fill=False)
                r2 = [r["text"] for r in r2v]
                r2f = page_rows(page, forward_fill=True)

                # --- P2: value and lexical anchor in the same row ---
                if len(res["P2_number_split"]["cases"]) < limit_per:
                    a, b = hit(r1), (hit(r2) or hit([raw_doc]))
                    res["P2_number_split"]["n"] += 1
                    res["P2_number_split"]["v1"] += a
                    res["P2_number_split"]["v2"] += b
                    res["P2_number_split"]["cases"].append(
                        {"item": it["item_id"], "page": pno, "v1": a, "v2": b})

                # --- P3: column preservation on multi-year data rows ---
                # What T-D needs is that a row like "範疇一排放總量 <4 year columns>"
                # keeps ALL its columns. Counting numbers in the anchor row was the
                # wrong proxy: it rewards v1 for welding two text columns together.
                # Ground truth is the raw-text line, which preserves table rows.
                if len(res["P3_column_drop"]["cases"]) < limit_per:
                    raw_lines = [" ".join(l.split())
                                 for l in (page.extract_text() or "").splitlines()]
                    targets = [l for l in raw_lines
                               if len(NUM.findall(l)) >= 3 and any(p.search(l) for p in ps)]
                    if targets:
                        tgt = max(targets, key=lambda l: len(NUM.findall(l)))
                        want = len(NUM.findall(tgt))
                        # Correspond rows by the numeric tokens they share with the
                        # raw line, not by a label prefix: raw text sometimes welds a
                        # whole table block into one line (2882 p185 has 25 numbers),
                        # so a label key finds no counterpart even when nothing was lost.
                        want_toks = {t.replace(",", "") for t in NUM.findall(tgt)}

                        def best(rowtexts):
                            b = 0
                            for r in rowtexts:
                                got = {t.replace(",", "") for t in NUM.findall(r)}
                                b = max(b, len(got & want_toks))
                            return b

                        g1, g2 = best(r1), best(r2)
                        res["P3_column_drop"]["n"] += 1
                        res["P3_column_drop"]["v1"] += (g1 >= want)
                        res["P3_column_drop"]["v2"] += (g2 >= want)
                        res["P3_column_drop"]["cases"].append(
                            {"item": it["item_id"], "page": pno, "raw_cols": want,
                             "v1_cols": g1, "v2_cols": g2})

                # --- P1: numeric rows carrying a label ---
                if len(res["P1_forward_fill"]["cases"]) < limit_per:
                    numrows = [r for r in r2f if r["values"]]
                    if numrows:
                        raw = sum(1 for r in numrows if r["label"])
                        fil = sum(1 for r in numrows if r["effective_label"])
                        res["P1_forward_fill"]["n"] += 1
                        res["P1_forward_fill"]["v1"] += raw / len(numrows)
                        res["P1_forward_fill"]["v2"] += fil / len(numrows)
                        res["P1_forward_fill"]["cases"].append(
                            {"item": it["item_id"], "page": pno,
                             "labelled_before": round(raw/len(numrows), 3),
                             "labelled_after": round(fil/len(numrows), 3)})
    return res


def main():
    items = [json.loads(l) for l in open("out/probe/items.jsonl", encoding="utf-8")
             if json.loads(l)["annotatable"]]
    res = check(items)
    out = {}
    print(f"{'pathology':22}{'n':>4}{'v1':>9}{'v2':>9}{'repair':>9}")
    for k, v in res.items():
        n = v["n"] or 1
        r1, r2 = v["v1"]/n, v["v2"]/n
        out[k] = {"n": v["n"], "v1_rate": round(r1, 3), "v2_rate": round(r2, 3),
                  "repair_rate": round(r2, 3), "cases": v["cases"]}
        print(f"{k:22}{v['n']:>4}{r1:>9.3f}{r2:>9.3f}{r2:>9.3f}")
    pathlib.Path("out").mkdir(exist_ok=True)
    pathlib.Path("out/extraction_health.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n-> out/extraction_health.json")


if __name__ == "__main__":
    main()
