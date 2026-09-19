"""filing_lookup backed by the PERTURBED snapshot (INV-9).

The evaluation harness must never reach the live regulator API: a system could
diff its answer against reality and detect the perturbation. This module reads a
static file and has no network code at all.
"""
import json, pathlib
from dataclasses import dataclass

_SNAP = json.loads(pathlib.Path("data/benchmark/filing_snapshot.json").read_text(encoding="utf-8"))


@dataclass
class FiledValue:
    value: float | None
    unit: str
    scope: str
    consolidation: str
    period: str


def filing_lookup(item_id: str) -> FiledValue | None:
    """None means the metric is not filed -- NOT that its value is zero (INV-2)."""
    r = _SNAP.get(item_id)
    if r is None or r.get("value") is None:
        return None
    return FiledValue(r["value"], r["unit"], r["scope"], r["consolidation"], r["period"])
