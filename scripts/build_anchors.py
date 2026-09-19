"""TASK-04R: construct the self-evidencing anchor set (gold source G-B).

An anchor is a (company, metric, page, span) quadruple where the FILED value
appears verbatim in the narrative. No judgement is involved: the four conditions
of construction_v1.md §3 are string and arithmetic tests.

  C1  every significant digit equal after unit normalisation   (tolerance 0)
  C2  significant digits >= 4
  C3  not a round number: excludes 10^k and {1,2,5}x10^k
  C4  within +/-200 characters of a lexical anchor for that metric

INV-3: every (company, metric) pair with a filed value is enumerated. Failing
C1-C4 marks an item "not verbatim-restated" -- it is never dropped, because that
outcome is itself the descriptive result (verbatim non-restatement rate).

INV-8: no language model appears anywhere in this file.
"""
import json, math, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pymupdf
from t3_yield import METRICS, _load, _num

CFG = json.loads(pathlib.Path("config/anchor_rules.json").read_text(encoding="utf-8"))
SCALES = CFG["unit_scales"]["values"]
WINDOW = CFG["conditions"]["C4_lexical_anchor_window_chars"]
MIN_SIG = CFG["conditions"]["C2_min_significant_digits"]
LEX = {m: [re.compile(p) for p in ps] for m, ps in CFG["lexical_anchors"].items()}
NUM = re.compile(r'\d[\d,]*(?:\.\d+)?')
SEED = 20260914


def sig_digits(tok: str) -> int:
    s = tok.replace(",", "").replace(".", "").lstrip("0").rstrip("0")
    return len(s) if s else 1


def is_round(x: float) -> bool:
    """C3: reject 10^k and {1,2,5}x10^k -- the shapes that produced every
    coincidental match in TASK-01 (ISO 14001, GRI 301, IPCC 2006, year 2025)."""
    if x == 0:
        return True
    a = abs(x)
    e = math.floor(math.log10(a))
    mant = a / (10 ** e)
    return any(abs(mant - m) < 1e-9 for m in (1.0, 2.0, 5.0))


def exact_match(tok: str, target: float):
    """C1: the token, at some unit scale, equals the target on every significant
    digit the token carries. Returns the scale, or None."""
    try:
        v = float(tok.replace(",", ""))
    except ValueError:
        return None
    if v == 0:
        return None
    d = sig_digits(tok)
    for s in SCALES:
        x = v * s
        if x == 0:
            continue
        e = math.floor(math.log10(abs(x)))
        q = 10 ** (e - d + 1)                      # the token's own resolution
        if abs(round(x / q) - round(target / q)) < 1e-9:
            return s
    return None


def page_texts(pdf_path):
    doc = pymupdf.open(pdf_path)
    out = [" ".join(doc[i].get_text().split()) for i in range(doc.page_count)]
    doc.close()
    return out


def filed_values(code):
    tables = {t: _load(t) for t in {m[0] for m in METRICS.values()}}
    out = {}
    for mid, (t, field, _v) in METRICS.items():
        rec = next((r for r in tables[t] if r["公司代號"] == code), None)
        if rec is None:
            continue
        v = _num(rec.get(field))
        if v is not None and v != 0:
            out[mid] = (v, rec)
    return out


def scan_company(code, pdf_path, corroborate=True):
    """Return one record per filed metric: anchor found, or explicitly not."""
    pages = page_texts(pdf_path)
    recs, stats = [], {"num_tokens": 0, "round_tokens": 0, "window_tokens": []}
    for txt in pages:
        toks = NUM.findall(txt)
        stats["num_tokens"] += len(toks)
        for t in toks:
            try:
                if is_round(float(t.replace(",", ""))):
                    stats["round_tokens"] += 1
            except ValueError:
                pass

    for mid, (target, rec) in filed_values(code).items():
        pats = LEX.get(mid, [re.compile(re.escape(mid))])
        hits = []
        for pno, txt in enumerate(pages, 1):
            anchors = [m.start() for p in pats for m in p.finditer(txt)]
            if not anchors:
                continue
            for m in NUM.finditer(txt):
                tok = m.group(0)
                if sig_digits(tok) < MIN_SIG:                      # C2
                    continue
                try:
                    if is_round(float(tok.replace(",", ""))):      # C3
                        continue
                except ValueError:
                    continue
                if not any(abs(m.start() - a) <= WINDOW for a in anchors):   # C4
                    continue
                sc = exact_match(tok, target)                      # C1
                if sc is None:
                    continue
                hits.append({"page": pno, "span": [m.start(), m.end()],
                             "value_verbatim": tok, "scale": sc,
                             "sig_digits": sig_digits(tok),
                             "anchor_offset": min(abs(m.start() - a) for a in anchors)})
                if not corroborate:
                    break
            if hits and not corroborate:
                break
        # window density, for the false-match bound
        for pno, txt in enumerate(pages, 1):
            anchors = [m.start() for p in pats for m in p.finditer(txt)]
            for a in anchors[:3]:
                seg = txt[max(0, a - WINDOW): a + WINDOW]
                stats["window_tokens"].append(len(NUM.findall(seg)))

        recs.append({
            "company_id": code, "metric_id": mid, "fiscal_year": 2025,
            "filed": {"value": target, "period": rec["報告年度"]},
            "anchor": hits[0] if hits else None,
            "corroborated_at": hits[1:] if len(hits) > 1 else [],
            "verbatim_restated": bool(hits),
            "gold_source": "G-B" if hits else None,
        })
    return recs, stats


def negative_control(code_a, code_b, pdf_a):
    """Cross-company control: does company A's report contain company B's filed
    values under C1-C4? Every acceptance here is a false match."""
    pages = page_texts(pdf_a)
    passed = total = 0
    for mid, (target, _r) in filed_values(code_b).items():
        pats = LEX.get(mid, [re.compile(re.escape(mid))])
        total += 1
        found = False
        for txt in pages:
            anchors = [m.start() for p in pats for m in p.finditer(txt)]
            if not anchors:
                continue
            for m in NUM.finditer(txt):
                tok = m.group(0)
                if sig_digits(tok) < MIN_SIG:
                    continue
                try:
                    if is_round(float(tok.replace(",", ""))):
                        continue
                except ValueError:
                    continue
                if not any(abs(m.start() - a) <= WINDOW for a in anchors):
                    continue
                if exact_match(tok, target) is not None:
                    found = True
                    break
            if found:
                break
        passed += (not found)          # rejected = control passed
    return passed, total
