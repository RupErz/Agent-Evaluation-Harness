# Design notes: regression vs. variance

This is the part of the harness that matters most, so it is worth stating the
reasoning in full. The goal is to tell a *real* regression (the change made the
agent worse) apart from *noise* (the model is non-deterministic and would have
wobbled anyway).

## Step 1 — eliminate the variance that isn't the model's

Before measuring model variance we remove every other source of it:

- **Frozen clock.** `FROZEN_NOW = 2026-08-15T12:00:00` is injected into the agent
  context and every tool. "Last month" resolves to July 2026 today and in six
  months. The agent never calls `datetime.now()`.
- **Committed fixture.** The SQLite DB is seeded from a version-controlled JSON
  file by a deterministic, seeded generator. The data cannot drift.
- **Pinned model.** `AGENT_MODEL` is a *dated snapshot* (`claude-haiku-4-5-20251001`),
  never an alias like `claude-haiku-4-5`. An alias can silently move under you and
  invalidate the baseline — which would defeat the entire project.
- **`temperature = 0`.** This SDK generation removed `temperature` as a named
  parameter; Haiku 4.5 still honours it via `extra_body`, so we genuinely pin it.
  Newer models (e.g. the Sonnet 5 judge) reject it and are left at their default —
  see `sampling_extra_body` in `config.py`.

Everything that remains is **genuine model variance**, which is what we want to
measure. `temperature = 0` *reduces* but does **not** eliminate it: the same
request can still produce different tool sequences or wording across runs. We do
not claim determinism we don't have.

## Step 2 — the baseline

`baseline.json` records, per case, the pass count out of `k`, plus the model
string and the date. It is committed and regenerated **only** deliberately via
`--write-baseline` (and, per our build order, only after mutation testing passes
— recording a baseline before the suite is proven just enshrines whatever the
agent happened to do that day).

## Step 3 — the decision rule

### Per case — Wilson score interval (a triage flag, not a verdict)

For a baseline of `passes` out of `k`, we compute the
[Wilson score interval](https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval#Wilson_score_interval)
on the proportion at 95%. A new run is **flagged** when its pass rate falls below
the interval's lower bound.

Wilson (rather than the normal approximation) because `k` is tiny and the
proportions live near 0 and 1, where the normal approximation is worst. Concretely
at `k = 5`:

| baseline | Wilson 95% lower bound | flags a new run at |
|---|---|---|
| 5/5 | ~0.566 | ≤ 2/5 |
| 4/5 | ~0.376 | ≤ 1/5 |

This is why a per-case comparison is a **triage flag, not a verdict**: at `k = 5`
it can only catch a large drop (roughly 100% → 20%). A case going 5/5 → 4/5 is
**not** evidence of anything.

### Suite level — two-proportion z-test (the number to trust)

We compare total passes across all cases — `n = k × case_count` (75 at `k = 5`) —
using a two-proportion z-test with a pooled variance estimate. The two-sided
p-value comes from the normal survival function (`math.erfc`). The suite is called
a regression when `p < 0.05` **and** the current rate is below the baseline rate.

The suite aggregate is the number to trust for "did this change make things worse
overall," because pooling 75 observations gives a meaningfully tighter interval
than any single case's 5.

## Step 4 — the honest limitation

At `k = 5`, the per-case test detects a drop from ~100% to ~20% and essentially
nothing subtler. Given more budget the fix is one of:

1. **Raise `k`** for the cases that matter most (injection, grounded correctness),
   accepting the token cost, or
2. Treat **per-case results as a debugging aid** and make the **suite aggregate the
   actual gate** — which is the stance this project takes.

We deliberately did **not** build a significance test we can't explain. A clearly
documented threshold rule beats a p-value nobody can defend in a conversation.

## A note on the LLM judge

Exactly one case (`F_closed_account_balance`) uses `JudgedBy`, because the thing
under test there is the *wording* ("did it clearly communicate it cannot answer").
The judge is:

- pinned to a **separate** model (`JUDGE_MODEL = claude-sonnet-5`), recorded distinctly;
- given a **binary** rubric, not a 1–5 score;
- run `k` times per repetition with a **majority** vote;
- **flagged distinctly** in the report, because it carries its own noise.

Everywhere else a mechanical check does the job (e.g. `MentionsNoneOf(["0.00"])`
for injection), and mechanical checks are always preferred.
