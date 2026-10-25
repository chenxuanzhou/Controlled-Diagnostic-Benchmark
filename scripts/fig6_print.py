"""Fig. 3 (effective numeric tolerance), camera-ready print version (2026-10-26).

Same data and design as scripts/fig6.py, but drawn at its printed size (0.7 of the
LNCS text width, 3.36 in) so that no lettering falls below the 6 pt Springer asks
for; a wider, shorter canvas keeps the vertical space the earlier version used.

usage: python scripts/fig6_print.py [sweep json] [output pdf]
default: out/tables/tolerance_sweep_fixed.json -> paper/figures/fig6_tolerance.pdf
"""
import json, pathlib, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
matplotlib.rcParams["pdf.fonttype"] = 42          # embed TrueType, not Type 3
matplotlib.rcParams.update({"font.size": 7, "axes.labelsize": 7, "xtick.labelsize": 6.5,
                            "ytick.labelsize": 6.5, "axes.linewidth": 0.6,
                            "xtick.major.width": 0.6, "ytick.major.width": 0.6})

SRC = sys.argv[1] if len(sys.argv) > 1 else "out/tables/tolerance_sweep_fixed.json"
OUT = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "paper/figures/fig6_tolerance.pdf")
D = json.loads(pathlib.Path(SRC).read_text(encoding="utf-8"))
EPS = json.loads(pathlib.Path("config/epsilon.json").read_text(encoding="utf-8"))["epsilon"] * 100
ACCENT, MUTED, ALERT = "#0E6E62", "#66766F", "#A83E27"

keys = sorted(D, key=float)
xs = [float(k) for k in keys]
ys = [D[k]["rate"] for k in keys]
lo = [D[k]["rate"] - D[k]["ci"][0] for k in keys]
hi = [D[k]["ci"][1] - D[k]["rate"] for k in keys]
ns = [D[k]["n"] for k in keys]

fig, ax = plt.subplots(figsize=(3.36, 1.5))
YTOP = 1.22
ax.axvspan(0.9, 1.2, ymax=(1.02 + 0.05) / (YTOP + 0.05), color="#E8C33A", alpha=0.22, zorder=0)
ax.errorbar(xs, ys, yerr=[lo, hi], fmt="o-", ms=3.2, lw=1.2, capsize=2, color=ACCENT,
            ecolor=MUTED, elinewidth=0.7, zorder=3)
ax.plot([EPS, EPS], [-0.05, 1.02], ls="--", lw=0.9, color=ALERT, zorder=2)
ax.text(EPS * 1.08, 0.5, f"declared\n$\\varepsilon$ = {EPS:g}%", color=ALERT, fontsize=7, fontweight="bold")
for i, (x, n) in enumerate(zip(xs, ns)):              # staggered so neighbours never collide
    ax.annotate(f"n={n}", (x, 1.16 if i % 2 == 0 else 1.075), ha="center", va="center",
                fontsize=6.2, color="#3A4A47")
ax.set_xscale("log")
ax.set_xticks(xs)
ax.set_xticklabels([f"{x:g}" for x in xs])
ax.minorticks_off()
ax.set_xlim(0.072, 22)
fig.canvas.draw()                                   # tick texts exist only after a draw
labs = ax.get_xticklabels()
labs[xs.index(1.2)].set_horizontalalignment("left")    # 0.9 and 1.2 sit close on the log axis
ax.set_xlabel(r"injected $|\delta|$ (%, log scale)", labelpad=1.5)
ax.set_ylabel("fraction SUPPORTED", labelpad=2)
ax.set_ylim(-0.05, YTOP)
ax.set_yticks([0, 0.5, 1.0])
ax.grid(alpha=0.22, lw=0.4)
fig.tight_layout(pad=0.2)
fig.savefig(OUT)
fig.savefig(OUT.with_suffix(".png"), dpi=600)
print(f"-> {OUT}")
for x, y, n in zip(xs, ys, ns):
    print(f"   delta={x:>5g}%  n={n:2d}  supported={y:.3f}")
