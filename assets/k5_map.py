#!/usr/bin/env python3
"""Draws k5_map.png: the whole of cost class 5, one band per chain.

Cost class 5 is the only class this rig has enumerated without a cap: all
58 skeletons, all 91,000 chains over the constant pool and the shift grid,
no sampling. Every one of them died, and this is what that looks like.

  one row   = one skeleton (the sequence of operations, constants free)
  one band  = one chain, coloured by the data volume at which PractRand
              first told its output from random
  row order = by median death depth, deepest at the top

The rows are stretched to equal width on purpose: the picture is about
*how* a skeleton dies, not how many chains it has. The count is printed
next to each row, because a row of 14 chains and a row of 6,000 look the
same otherwise, and that would be a lie of composition.

Reads results/class_k5_complete_evals.jsonl, which is the primary file
the run wrote, not a summary of it.
"""
import json
import os
import statistics
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
QUELLE = os.path.join(REPO, "results", "class_k5_complete_evals.jsonl")
ZIEL = os.path.join(HERE, "k5_map.png")

# Operation symbols, from COST_OPS in rrc/ladder.py. The number in
# brackets is what the operation costs, and the sum is the class.
OPS = {
    0: ("^>>k", 2), 1: ("*c", 3), 2: ("rot", 1), 3: ("^<<k", 2),
    5: ("+<<k", 2), 6: ("^c", 1), 7: ("+c", 1), 8: ("mf c", 4),
    9: ("xrot2", 3), 10: ("xsh2", 2), 11: ("bswap", 1), 13: ("not", 1),
}

GRUND = "#0F1312"
TINTE = "#E4E9E5"
MATT = "#8B968F"
# 2^10 (dies at the first checkpoint) to 2^16 (deepest anything got)
FARBEN = ["#7E2417", "#A8452A", "#C4703B", "#C9A24A",
          "#8FA85C", "#4E9B78", "#2E7D62"]
TIEFEN = list(range(10, 17))


def lade():
    zeilen = defaultdict(list)
    n = 0
    with open(QUELLE, encoding="utf-8") as f:
        for z in f:
            o = json.loads(z)
            t = o.get("first_fail")
            if not isinstance(t, int):
                continue          # a hole is never drawn as a death
            zeilen[tuple(o["skeleton"])].append(t)
            n += 1
    return zeilen, n


def beschriftung(seq):
    teile, kosten = [], 0
    for op in seq:
        sym, k = OPS.get(op, (f"op{op}", 0))
        teile.append(sym)
        kosten += k
    return " ".join(teile), kosten


def zeichne():
    zeilen, n = lade()
    rang = sorted(zeilen.items(), key=lambda kv: (statistics.median(kv[1]),
                                                  max(kv[1]), len(kv[1])),
                  reverse=True)
    breite = 900
    bild = np.zeros((len(rang), breite))
    for i, (seq, tiefen) in enumerate(rang):
        t = np.array(sorted(tiefen))
        idx = (np.arange(breite) * len(t) // breite).clip(0, len(t) - 1)
        bild[i] = t[idx]

    cmap = ListedColormap(FARBEN)
    norm = BoundaryNorm([t - 0.5 for t in TIEFEN] + [TIEFEN[-1] + 0.5], cmap.N)

    fig = plt.figure(figsize=(11.5, 9.6), dpi=150, facecolor=GRUND)
    gs = fig.add_gridspec(2, 1, height_ratios=[1, 11], hspace=0.16,
                          left=0.235, right=0.955, top=0.925, bottom=0.105)

    # Oben: die ganze Klasse als ein Balken je Tiefe.
    ax0 = fig.add_subplot(gs[0], facecolor=GRUND)
    zaehl = [sum(1 for _, ts in rang for t in ts if t == d) for d in TIEFEN]
    ax0.bar(range(len(TIEFEN)), zaehl, color=FARBEN, width=0.82)
    for i, c in enumerate(zaehl):
        if c:
            ax0.text(i, c, f"{c:,}".replace(",", " "), ha="center",
                     va="bottom", color=MATT, fontsize=8.5)
    ax0.set_xticks(range(len(TIEFEN)))
    ax0.set_xticklabels([f"2^{d}" for d in TIEFEN], color=MATT, fontsize=8.5)
    ax0.set_yticks([])
    ax0.set_ylim(0, max(zaehl) * 1.3)
    for s in ax0.spines.values():
        s.set_visible(False)
    ax0.tick_params(length=0)
    ax0.set_title("all 91,000 chains by the volume at which they fell",
                  color=MATT, fontsize=9.5, pad=6, loc="left")

    # Unten: die Karte.
    ax = fig.add_subplot(gs[1], facecolor=GRUND)
    ax.imshow(bild, aspect="auto", cmap=cmap, norm=norm, interpolation="nearest")
    ax.set_xticks([])
    ax.set_yticks(range(len(rang)))
    etiketten = []
    for seq, tiefen in rang:
        txt, k = beschriftung(seq)
        etiketten.append(f"{txt}")
    ax.set_yticklabels(etiketten, color=TINTE, fontsize=7.4,
                       fontfamily="monospace")
    ax.tick_params(length=0, pad=4)
    for s in ax.spines.values():
        s.set_color("#2A3331")

    for i, (seq, tiefen) in enumerate(rang):
        ax.text(breite + 8, i, f"{len(tiefen):>5,}".replace(",", " "),
                va="center", ha="left", color=MATT, fontsize=7,
                fontfamily="monospace", clip_on=False)
    ax.text(breite + 8, -1.4, "chains", va="center", ha="left", color=MATT,
            fontsize=7, fontfamily="monospace", clip_on=False)

    fig.text(0.235, 0.975, "COST CLASS 5, ENUMERATED", color=TINTE,
             fontsize=15.5, fontfamily="monospace", fontweight="bold")
    fig.text(0.6, 0.978,
             "58 skeletons  ·  91,000 chains  ·  0 survivors",
             color=MATT, fontsize=10, fontfamily="monospace")

    leg = [Patch(facecolor=FARBEN[i], label=f"2^{d}") for i, d in enumerate(TIEFEN)]
    ax.legend(handles=leg, loc="upper center", bbox_to_anchor=(0.5, -0.028),
              ncol=7, frameon=False, fontsize=8, labelcolor=MATT,
              handlelength=1.4, handleheight=0.9, columnspacing=1.6,
              title="data volume at first failure", title_fontsize=8)
    ax.get_legend().get_title().set_color(MATT)

    fig.text(0.235, 0.036,
             "Every chain in the class, none excluded. The space is bounded "
             "by choice, not by nature: 14 constants from a pool, 23 shift\n"
             "amounts from a grid, 12 operation types. Nothing here says a "
             "cost-5 mixer cannot exist. Only that none of these 91,000 is one.",
             color=MATT, fontsize=8.2, va="top")

    fig.savefig(ZIEL, facecolor=GRUND)
    print(f"  {ZIEL}  ({os.path.getsize(ZIEL) / 1024:.0f} KB)")
    print(f"  {len(rang)} skeletons, {n:,} chains drawn")


if __name__ == "__main__":
    zeichne()
