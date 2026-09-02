# meer10

The datasheet of one that does not: the cheapest chain known to
us that passes RRC-64-40, including where it is weaker than the
mixer it outperforms.

The paper is [`MEER10.pdf`](MEER10.pdf). **There is no code in this folder.**

The mixer itself is [`../meer10.h`](../meer10.h). Whether that header
is the function the measurements were made with is checked by
[`../verify_meer10.c`](../verify_meer10.c): known-answer vectors,
bijectivity on a large sample, and — if the rig is present — a
word-for-word comparison against `rrc/feeder.exe`. A skipped check is
reported as skipped and never counted as a pass.

The rig that produced these numbers is in [`../rrc/`](../rrc/) —
`ladder.py` drives it, `feeder.cpp` feeds PractRand. The measurements
it wrote are in [`../results/`](../results/), and a paper is checked
against those, not against its typesetter.

The [repository README](../README.md) says how the papers, the rig and
the data fit together.
