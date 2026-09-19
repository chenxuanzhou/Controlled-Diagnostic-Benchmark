"""Fig.6: effective numeric tolerance, aggregate curve with binomial CIs.

The earlier version plotted seven per-condition series over the same 128 sweep
items, so several cells held n=2-3 and the curve the text quotes was not the
curve drawn. This plots the aggregate the text actually cites, annotates n at
every point, and shows Wilson intervals.
"""
import json, pathlib, sys
sys.path.insert(0, "scripts")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
matplotlib.rcParams["pdf.fonttype"] = 42   # embed TrueType, not Type 3 (publisher requirement)

# optional: python scripts/fig6.py <sweep json> <output stem>
SRC = sys.argv[1] if len(sys.argv) > 1 else "out/tables/tolerance_sweep.json"
STEM = sys.argv[2] if len(sys.argv) > 2 else "fig6_tolerance"
D = json.loads(pathlib.Path(SRC).read_text(encoding="utf-8"))
EPS = json.loads(pathlib.Path("config/epsilon.json").read_text(encoding="utf-8"))["epsilon"] * 100
ACCENT, MUTED, ALERT = "#0E6E62", "#66766F", "#A83E27"

keys = sorted(D, key=float)
xs = [float(k) for k in keys]
ys = [D[k]["rate"] for k in keys]
lo = [D[k]["rate"] - D[k]["ci"][0] for k in keys]
hi = [D[k]["ci"][1] - D[k]["rate"] for k in keys]
ns = [D[k]["n"] for k in keys]

fig, ax = plt.subplots(figsize=(6.4, 3.6))
YTOP = 1.2
ax.axvspan(0.9, 1.2, ymax=(1.02 + 0.05) / (YTOP + 0.05), color="#E8C33A", alpha=0.20, zorder=0)
ax.errorbar(xs, ys, yerr=[lo, hi], fmt="o-", ms=6, lw=2.0, capsize=3.5,
            color=ACCENT, ecolor=MUTED, elinewidth=1.1, zorder=3)
ax.plot([EPS, EPS], [-0.05, 1.02], ls="--", lw=1.5, color=ALERT, zorder=2)
ax.text(EPS * 1.07, 0.55, f"declared\n$\\varepsilon$ = {EPS:g}%",
        color=ALERT, fontsize=9.5, fontweight="bold")

# n labels sit above the plot area, staggered over two rows, so they collide
# neither with the error bars nor with each other around epsilon.
for i, (x, n) in enumerate(zip(xs, ns)):
    ax.annotate(f"n={n}", (x, 1.145 if i % 2 == 0 else 1.065), ha="center",
                va="center", fontsize=8, color="#3A4A47")

ax.set_xscale("log")
ax.set_xticks(xs)
ax.set_xticklabels([f"{x:g}" for x in xs], fontsize=9)
ax.set_xlabel(r"injected $|\delta|$  (%, log scale)")
ax.set_ylabel("fraction judged SUPPORTED")
ax.set_ylim(-0.05, YTOP)
ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
ax.grid(alpha=0.22, lw=0.6)
fig.tight_layout()
out = pathlib.Path(f"out/figures/{STEM}.png")
fig.savefig(out, dpi=300)
fig.savefig(out.with_suffix(".pdf"))   # vector copy used by the paper
print(f"-> {out}")
for x, y, n in zip(xs, ys, ns):
    print(f"   delta={x:>5g}%  n={n:2d}  supported={y:.3f}")
