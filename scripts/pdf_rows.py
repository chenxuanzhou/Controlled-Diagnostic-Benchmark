"""Coordinate row reconstruction, v2 -- fixes the three extraction pathologies
measured in TASK-01.

  P1  hierarchical labels not forward-filled   (a continuation row loses 範疇一)
  P2  numbers split away from their label      (2303, 2610)
  P3  columns dropped from a reconstructed row (2002 p24: 4 headers, 3 values)

P2 and P3 share a root cause: the v1 clustering used one fixed y-tolerance over
the whole page and ignored column layout. On a two-column page it welds the left
and right columns into one "row"; where a figure sits on a slightly different
baseline from its label, it lands in a neighbouring row instead. The fix is to
segment columns first, then cluster rows inside each column with a tolerance
derived from the local font size.
"""
import re
import statistics

NUM = re.compile(r'\d[\d,]*(?:\.\d+)?')


def _column_blocks(words, min_gap_ratio=0.035, page_width=None):
    """Split words into column blocks by looking for wide vertical gutters.

    A gutter is an x-interval covered by no word and wider than min_gap_ratio of
    the page. Two-column report layouts produce exactly one such gutter.
    """
    if not words:
        return []
    page_width = page_width or max(w["x1"] for w in words)
    spans = sorted((w["x0"], w["x1"]) for w in words)
    merged = [list(spans[0])]
    for a, b in spans[1:]:
        if a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    gutters = [(merged[i][1], merged[i + 1][0]) for i in range(len(merged) - 1)
               if merged[i + 1][0] - merged[i][1] >= min_gap_ratio * page_width]
    if not gutters:
        return [words]
    cuts = [0.0] + [(g0 + g1) / 2 for g0, g1 in gutters] + [page_width + 1]
    blocks = []
    for lo, hi in zip(cuts, cuts[1:]):
        b = [w for w in words if lo <= (w["x0"] + w["x1"]) / 2 < hi]
        if b:
            blocks.append(b)
    return blocks


def _cluster_rows(words):
    """Cluster one column block into rows using a font-size-derived tolerance."""
    if not words:
        return []
    heights = [w["bottom"] - w["top"] for w in words]
    tol = max(1.5, statistics.median(heights) * 0.6)
    for w in words:
        w["_mid"] = (w["top"] + w["bottom"]) / 2
    ws = sorted(words, key=lambda w: (w["_mid"], w["x0"]))
    rows, cur, ref = [], [ws[0]], ws[0]["_mid"]
    for w in ws[1:]:
        if abs(w["_mid"] - ref) <= tol:
            cur.append(w)
            ref = statistics.mean(x["_mid"] for x in cur)
        else:
            rows.append(sorted(cur, key=lambda x: x["x0"]))
            cur, ref = [w], w["_mid"]
    rows.append(sorted(cur, key=lambda x: x["x0"]))
    return rows


def page_rows(page, forward_fill=True):
    """Return the page as a list of row dicts, column-aware and label-filled."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    out = []
    for block in _column_blocks(words, page_width=page.width):
        rows = _cluster_rows(block)
        carried = ""
        for r in rows:
            toks = [w["text"] for w in r]
            text = " ".join(toks)
            label = " ".join(t for t in toks if not NUM.fullmatch(t.replace(",", "")))
            nums = [t for t in toks if NUM.fullmatch(t.replace(",", ""))]
            if forward_fill:
                if label.strip():
                    carried = label.strip()
                    eff = carried
                else:
                    eff = carried            # continuation row inherits the parent label
            else:
                eff = label.strip()
            out.append({"text": text, "label": label.strip(), "effective_label": eff,
                        "values": nums, "top": min(w["top"] for w in r),
                        "x0": min(w["x0"] for w in r)})
    out.sort(key=lambda r: (r["top"], r["x0"]))
    return out


def row_texts(page, forward_fill=True):
    return [r["text"] for r in page_rows(page, forward_fill)]
