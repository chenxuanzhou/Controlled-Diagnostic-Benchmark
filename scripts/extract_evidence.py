"""Pull compact evidence snippets for each probe item, for human adjudication.

Lines are reconstructed by coordinate clustering, not by raw text order: borderless
tables put a row label and its values on separate text lines, so naive line reading
loses exactly the rows that matter (D-6, same root cause as the line-based table
detector failing in Gate 0).

Value agreement is never used for ranking (INV-3) -- a CONTRADICTED item must
surface just as readily as a SUPPORTED one.
"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pdfplumber
from t3_yield import METRICS, NUMTOK, UNIT_HINT, _sigdigits
from pdf_probe import rows_by_coords


def snippets(pdf_path, item, max_lines=4, width=150):
    _, _, vocab = METRICS[item["metric_id"]]
    pages_wanted = item["evidence"]["candidate_pages"]
    if item.get("locator_hint"):
        hp = item["locator_hint"]["page"]
        if hp not in pages_wanted:
            pages_wanted = [hp] + pages_wanted
    scored = []
    with pdfplumber.open(pdf_path) as pdf:
        for pno in pages_wanted:
            page = pdf.pages[pno - 1]
            for row in rows_by_coords(page):
                line = " ".join(w["text"] for w in row)
                line = " ".join(line.split())
                if len(line) < 4:
                    continue
                v = sum(1 for k in vocab if k in line)
                nums = [t for t in NUMTOK.findall(line) if _sigdigits(t) >= 2]
                if v and nums and UNIT_HINT.search(line):
                    scored.append((v * 10 + min(len(nums), 5), pno, line[:width]))
    scored.sort(key=lambda x: -x[0])
    seen, out = set(), []
    for _, pno, line in scored:
        if line in seen:
            continue
        seen.add(line)
        out.append((pno, line))
        if len(out) >= max_lines:
            break
    return out


def _pick(company, kind):
    """Return whichever wave file holds this company."""
    import pathlib, json as _j
    for f in (f"out/probe/{kind}.jsonl", f"out/probe/{kind}_w2.jsonl"):
        p = pathlib.Path(f)
        if p.exists() and any(_j.loads(l)["company_id"] == company
                              for l in p.open(encoding="utf-8")):
            return f
    raise SystemExit(f"{company} not found in any {kind} file")


def main(company, max_lines=4):
    items = [json.loads(l) for l in
             open(_pick(company, "items_skeleton"), encoding="utf-8")
             if json.loads(l)["company_id"] == company]
    pdf = f"data/raw_pdf/{company}_2025.pdf"
    for it in items:
        f = it["filed"]
        cons = (f["consolidation"] or "")[:34]
        print(f"\n### {it['item_id']}")
        print(f"    FILED {f['value']:>16,.4f} {f['unit']:<12} 邊界={cons!r} 驗證={f['assurance']}")
        if it["locator_hint"]:
            h = it["locator_hint"]
            print(f"    HINT  p{h['page']} text={h['text']} x{h['scale']:g} err={h['rel_err']*100:.3f}%")
        sn = snippets(pdf, it, max_lines)
        if not sn:
            print("    (no evidence lines)")
        for pno, line in sn:
            print(f"    p{pno:<4} {line}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 4)
