# The Anchors

The calibration weights: mix13 and fmix64 measured on this rig,
cross-checked against Evensen's published ranges. And the day
this rig's own anchor deleted four of its own logs.

The paper is [`ANCHOR.pdf`](ANCHOR.pdf). **There is no code in this folder.**

The measurement this paper is built on is next to it:
[`measurement_2026-08-24.json`](measurement_2026-08-24.json).

The rig that produced these numbers is in [`../rrc/`](../rrc/) —
`ladder.py` drives it, `feeder.cpp` feeds PractRand. The measurements
it wrote are in [`../results/`](../results/), and a paper is checked
against those, not against its typesetter.

The [repository README](../README.md) says how the papers, the rig and
the data fit together.
