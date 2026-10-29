Every step of a process uses something: tokens of a language model, time on a computer, calls
to another system. Taktus records what each step used. From those records you see where a
process spends, and you compare two runs before a change is kept.

## Where one run spent

Open a run in the web app and follow *where it spent*. The page shows each step with its money
and its Takte. A Takt is Taktus's own unit for the work a step did, whatever it ran on. Two
charts show the steps side by side: one for money, one for the tokens a language model read and
wrote. The token chart splits each step by what the tokens cost: plain input, cache writes,
cache reads and output. Below the charts, every figure is written out as text.

Money is computed at the prices that applied when the run started, not at today's prices. A
figure that cannot be priced says *not priced*. It never shows as zero.

## Where a process spends over time

The process's page in the web app links to *where it spends*. It adds up every run of the last
7, 30 or 90 days, step by step. You choose the window.

## Two runs side by side

A change, such as another model or a shorter prompt, is kept only when it is shown to be better.
On a run's spend page, give the identifier of a second run of the same task. Taktus shows both
runs on the same scale, the difference per step, and whether each step produced the same result.

## In the chat

If you are the owner, or someone the owner named, you can ask in the owner's conversation:

- `spend <run>` for one run, step by step;
- `spend <run> <other run>` for two runs side by side;
- `spend process <process>` for a process over the last thirty days.

Taktus answers with the figures and a link to the same page in the web app. In German, the words
are `kosten` and `kosten prozess`.

## Trying a model before it is chosen

Before a language model is used for a kind of work, Taktus offers a **trial**. It offers one when
a model is new, when Taktus proposes another, and when the provider changes the model's version.
The web app lists the offers under *Trials*. A trial runs the same test cases once with each
model. These are rehearsals: nothing outside Taktus is touched. The trial's page then shows, per
model, how many cases passed, what it cost, how many tokens it used, how long it took, and each
result beside the others.

A trial decides nothing. Which model does the work stays a person's decision.

## What these figures never show

No figure here is about a person. Taktus measures runs, steps and processes, never who started
them.
