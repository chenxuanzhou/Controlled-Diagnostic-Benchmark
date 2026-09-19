"""TASK-09R/10R: figures and tables from the scored runs.

Fig.3  accuracy vs overclaim rate            -> P3
Fig.6  effective numeric tolerance curve     -> contribution #3
Tab.3  T-B results by condition
Tab.4  injected perturbation x predicted mismatch_type (confusion)  -> P2
Tab.5  tool ablation                         -> P2, cleanest evidence
"""
import collections, json, pathlib, sys
sys.path.insert(0, "scripts")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from score import load_gold, parse, wilson

OUT = pathlib.Path("out/figures"); OUT.mkdir(parents=True, exist_ok=True)
TAB = pathlib.Path("out/tables"); TAB.mkdir(parents=True, exist_ok=True)
RUNS = pathlib.Path("out/runs")
ACCENT, ALERT, MUTED = "#0E6E62", "#A83E27", "#66766F"


def load(path, label=None):
    p = RUNS / path
    if not p.exists():
        return []
    rows = [json.loads(l) for l in p.open(encoding="utf-8")]
    if label:
        for r in rows:
            r["condition"] = label
    return rows


def cell_stats(rows, gold):
    n = correct = overclaim = nc = unparsed = 0
    conf = collections.Counter()
    mm = collections.Counter()
    byp = collections.defaultdict(lambda: [0, 0])
    tol = collections.defaultdict(lambda: [0, 0])
    tin = tout = 0
    for r in rows:
        if "error" in r:
            continue
        tin += r.get("prompt_tokens", 0); tout += r.get("completion_tokens", 0)
        g = gold.get(r["item_id"])
        if not g:
            continue
        pred, pmm = parse(r.get("content"))
        if pred is None:
            unparsed += 1
            continue
        n += 1
        correct += pred == g["verdict"]
        conf[(g["verdict"], pred)] += 1
        if g["verdict"] == "NOT_COMPARABLE":
            nc += 1
            overclaim += pred in ("SUPPORTED", "CONTRADICTED")
        byp[g["ptype"]][1] += 1; byp[g["ptype"]][0] += pred == g["verdict"]
        if g["mismatch_type"]:
            mm[(g["mismatch_type"], pmm)] += 1
        if g["ptype"] == "P-magnitude" and g["delta"] is not None:
            k = round(abs(g["delta"]) * 100, 1)
            tol[k][1] += 1; tol[k][0] += pred == "SUPPORTED"
    return {"n_scored": n, "unparsed": unparsed,
            "accuracy": correct / n if n else 0.0,
            "acc_ci": wilson(correct, n),
            "overclaim": overclaim / nc if nc else None,
            "overclaim_n": nc,
            "by_ptype": {k: (v[0] / v[1], v[1]) for k, v in byp.items()},
            "tol": {k: (v[0] / v[1], v[1]) for k, v in tol.items()},
            "mismatch": mm, "conf": conf,
            "tok_in": tin, "tok_out": tout, "n_calls": len(rows)}


def main():
    gold = load_gold()
    cells = {}
    for name, label in [("tb_text.jsonl", None), ("tb_c3.jsonl", "C3"),
                        ("tb_c4.jsonl", "C4"), ("tb_abl_lookup.jsonl", "C3-filing_lookup"),
                        ("tb_abl_calc.jsonl", "C3-calc")]:
        rows = load(name, label)
        if not rows:
            continue
        for cond in sorted({r.get("condition") for r in rows}):
            cells[cond] = cell_stats([r for r in rows if r.get("condition") == cond], gold)

    # ---------- Tab.3 ----------
    lines = ["| condition | n | accuracy | 95% CI | overclaim rate | unparsed |",
             "|---|---:|---:|---|---:|---:|"]
    for c, s in cells.items():
        oc = f"{s['overclaim']:.3f}" if s["overclaim"] is not None else "-"
        lines.append(f"| {c} | {s['n_scored']} | {s['accuracy']:.3f} | "
                     f"[{s['acc_ci'][0]:.3f}, {s['acc_ci'][1]:.3f}] | {oc} | {s['unparsed']} |")
    (TAB / "tab3_results.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

    # ---------- Tab.4 confusion ----------
    main_cell = "C3" if "C3" in cells else list(cells)[0]
    mm = cells[main_cell]["mismatch"]
    types = ["consolidation", "scope", "absolute_vs_intensity",
             "indistinguishable_metric", "cross_company"]
    preds = sorted({b for _, b in mm} | {None}, key=lambda x: (x is None, str(x)))
    l4 = [f"Tab.4 injected -> predicted mismatch_type ({main_cell})", "",
          "| injected \\ predicted | " + " | ".join(str(p) for p in preds) + " |",
          "|---" * (len(preds) + 1) + "|"]
    for t in types:
        row = [str(mm.get((t, p), 0)) for p in preds]
        if any(x != "0" for x in row):
            l4.append(f"| {t} | " + " | ".join(row) + " |")
    (TAB / "tab4_confusion.md").write_text("\n".join(l4), encoding="utf-8")
    print("\n" + "\n".join(l4))

    # ---------- Tab.5 ablation ----------
    if any(k.startswith("C3-") for k in cells):
        l5 = ["| configuration | n | accuracy | Δ vs full | overclaim |", "|---|---:|---:|---:|---:|"]
        base = cells.get("C3", {}).get("accuracy", 0)
        for c in ["C3"] + sorted(k for k in cells if k.startswith("C3-")):
            if c not in cells: continue
            s = cells[c]
            oc = f"{s['overclaim']:.3f}" if s["overclaim"] is not None else "-"
            d = "—" if c == "C3" else f"{s['accuracy']-base:+.3f}"
            l5.append(f"| {c} | {s['n_scored']} | {s['accuracy']:.3f} | {d} | {oc} |")
        (TAB / "tab5_ablation.md").write_text("\n".join(l5), encoding="utf-8")
        print("\n" + "\n".join(l5))

    # ---------- Fig.3 accuracy vs overclaim ----------
    pts = [(c, s) for c, s in cells.items() if s["overclaim"] is not None and s["n_scored"]]
    if pts:
        fig, ax = plt.subplots(figsize=(6.2, 4.4))
        for c, s in pts:
            sz = 40 + 260 * (s["tok_in"] + s["tok_out"]) / max(
                1, max(x["tok_in"] + x["tok_out"] for _, x in pts))
            ax.scatter(s["overclaim"], s["accuracy"], s=sz, color=ACCENT,
                       alpha=.75, edgecolor="white", lw=1.2, zorder=3)
            ax.annotate(c, (s["overclaim"], s["accuracy"]), fontsize=8.5,
                        xytext=(6, 5), textcoords="offset points", color="#3A4A47")
        ax.set_xlabel("overclaim rate  (definite verdict where gold is NOT_COMPARABLE)")
        ax.set_ylabel("verdict accuracy")
        ax.set_title("Fig.3  accuracy vs overclaim (marker size = tokens/item)", fontsize=10)
        ax.grid(alpha=.22, lw=.6)
        fig.tight_layout(); fig.savefig(OUT / "fig3_accuracy_overclaim.png", dpi=170)
        print(f"\n-> {OUT/'fig3_accuracy_overclaim.png'}")

    # ---------- Fig.6 tolerance curve ----------
    eps = json.loads(pathlib.Path("config/epsilon.json").read_text(encoding="utf-8"))["epsilon"]
    sweep = {}
    for c, s in cells.items():
        if s["tol"]:
            sweep[c] = s["tol"]
    sw = load("sweep_c1.jsonl", "C1-sweep")
    if sw:
        sweep["C1-sweep"] = cell_stats(sw, gold)["tol"]
    if sweep:
        fig, ax = plt.subplots(figsize=(6.4, 4.2))
        for i, (c, tol) in enumerate(sweep.items()):
            xs = sorted(tol)
            ys = [tol[x][0] for x in xs]
            ax.plot(xs, ys, marker="o", ms=5, lw=1.7, label=f"{c}",
                    color=[ACCENT, ALERT, "#8A6212", "#3A6EA8"][i % 4], zorder=3)
        ax.axvline(eps * 100, ls="--", lw=1.4, color=MUTED)
        ax.text(eps * 100 * 1.06, 0.05, f"declared ε = {eps*100:g}%", fontsize=9, color=MUTED)
        ax.set_xscale("log")
        ax.set_xlabel("injected |δ|  (%, log)")
        ax.set_ylabel("fraction judged SUPPORTED")
        ax.set_title("Fig.6  effective numeric tolerance", fontsize=10.5)
        ax.set_ylim(-0.03, 1.03); ax.grid(alpha=.22, lw=.6); ax.legend(fontsize=8.5)
        fig.tight_layout(); fig.savefig(OUT / "fig6_tolerance.png", dpi=170)
        print(f"-> {OUT/'fig6_tolerance.png'}")

    json.dump({c: {k: (v if not isinstance(v, collections.Counter)
                       else {f"{a}->{b}": n for (a, b), n in v.items()})
                   for k, v in s.items()} for c, s in cells.items()},
              (TAB / "cells.json").open("w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
