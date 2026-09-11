# Design notes: regression versus variance

This is the part of the harness that matters most, so it is worth walking through
the reasoning in full. The whole job here is to tell a real regression, where a
change actually made the agent worse, apart from ordinary noise, where the model is
not deterministic and would have wobbled on its own anyway.

## Step 1: remove the variance that is not the model's

Before we can measure how much the model itself varies, we take away every other
reason a run could come out different.

- **Frozen clock.** `FROZEN_NOW = 2026-08-15T12:00:00` is handed to the agent and to
  every tool that needs a date. "Last month" means July 2026 today, and it will
  still mean July 2026 six months from now. The agent never calls `datetime.now()`.
- **Committed fixture.** The SQLite database is built from a version controlled JSON
  file by a seeded generator that always produces the same data, so nothing about
  the data can quietly drift.
- **Pinned model.** `AGENT_MODEL` is a dated snapshot (`claude-haiku-4-5-20251001`),
  never a moving alias like `claude-haiku-4-5`. An alias can change under you without
  warning and quietly invalidate the baseline, which would defeat the entire point
  of the project.
- **`temperature = 0`.** This SDK generation dropped `temperature` as a named
  parameter, but Haiku 4.5 still honours it through `extra_body`, so we really do
  pin it. Newer models such as the Sonnet judge reject it and run at their own
  default. See `sampling_extra_body` in `config.py`.

Whatever is left after all of that is genuine model variance, and that is exactly
what we are trying to measure. Setting `temperature = 0` lowers that variance but
does not remove it. The same request can still come back with a different tool
sequence or different wording, so we are careful not to claim a determinism we do
not actually have.

## Step 2: the baseline

`baseline.json` records, for each case, how many of the `k` runs passed, along with
the model string and the date. It is committed to the repo and only ever regenerated
on purpose through `--write-baseline`. In our build order we write it only after
mutation testing passes, because recording a baseline before the suite is proven
just freezes in whatever the agent happened to do that day.

## Step 3: the decision rule

### Per case: the Wilson interval, a triage flag rather than a verdict

For a baseline of some number of passes out of `k`, we compute the
[Wilson score interval](https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval#Wilson_score_interval)
on that proportion at 95 percent. A new run gets flagged when its pass rate falls
below the lower bound of that interval.

We reach for Wilson rather than the normal approximation because `k` is tiny and the
pass rates sit right up near 0 and 1, which is exactly where the normal
approximation is at its worst. At `k = 5` it looks like this.

| baseline | Wilson 95 percent lower bound | flags a new run at |
|---|---|---|
| 5/5 | about 0.566 | 2/5 or lower |
| 4/5 | about 0.376 | 1/5 or lower |

This is why a per case comparison is a triage flag and not a verdict. At `k = 5` it
can only catch a large drop, roughly 100 percent down to 20 percent. A case slipping
from 5/5 to 4/5 tells you nothing on its own.

### Suite level: the two proportion z test, the number to trust

Here we compare total passes across every case, which is `k` times the number of
cases, so 75 runs at `k = 5`. We use a two proportion z test with a pooled variance
estimate, and the two sided p value comes from the normal survival function
(`math.erfc`). The suite counts as a regression when the p value is below 0.05 and
the current rate really is below the baseline rate.

The suite number is the one to trust when you ask whether a change made things worse
overall, because pooling 75 observations gives a much tighter interval than any
single case's 5 ever could.

## Step 4: the honest limitation

At `k = 5` the per case test can see a drop from about 100 percent to about 20
percent and basically nothing more subtle than that. With more budget there are two
honest ways forward.

1. Raise `k` on the cases you care about most, such as injection and grounded
   correctness, and accept the extra token cost.
2. Treat the per case results as a debugging aid and let the suite aggregate be the
   real gate. That is the stance this project takes.

We deliberately did not build a fancy significance test we cannot explain. A
threshold rule you can describe in one sentence beats a p value nobody can defend in
a conversation.

### The ceiling effect, or why every Wilson bound is the same

The current baseline passes 5/5 on every single case, so every per case Wilson lower
bound comes out to the same 57 percent at `k = 5`. Two things follow from that, and
both are worth saying out loud.

- The suite can spot regressions but not improvements, because there is no room above
  5/5 to move into.
- A regression has to be large to clear the interval. A case has to fall all the way
  to 2/5, which is 40 percent, before the per case check reacts.

That is fine and expected for a strong agent on a passing suite. It is also the
reason the mutation section carries the real weight of showing that the tests work.
An all green baseline only proves the agent behaves. It does not prove the suite
would notice if the agent stopped behaving.

## A note on the LLM judge

Exactly one case, `F_closed_account_balance`, uses `JudgedBy`, because the thing
actually under test there is the wording, whether the agent clearly communicates
that it cannot answer. The judge runs on a few deliberate rules.

- It is pinned to a separate model, `JUDGE_MODEL = claude-sonnet-5`, and recorded on
  its own.
- It gets a yes or no rubric rather than a 1 to 5 score.
- It runs `k` times for each repetition and takes the majority vote.
- It is flagged clearly in the report, because it carries noise of its own.

Everywhere else a mechanical check does the job. The injection cases, for example,
use `DoesNotReportZeroBalance`, which reads the reported numbers rather than guessing
at wording. A mechanical check wins whenever one is available.
