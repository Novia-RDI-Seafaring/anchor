# Agent Experience (AX) and AX testing

Most software is now used by agents as well as people. UX asks how easy a tool
is for a human. **AX (Agent Experience)** asks the same question for an agent.
ANCHOR treats AX as a first-class design dimension, on par with UX. Its three
peer adapters (CLI, MCP, HTTP) exist so an agent, a shell user, and a web UI all
reach the same operations with the same semantics.

This page describes how to *test* AX, the way usability testing validates UX.

## AX testing is usability testing with an agent as the subject

The protocol mirrors a UX usability test.

| Usability test (UX) | AX test |
| --- | --- |
| Recruit a representative user. | Spawn a fresh agent with only the real deployment surface: the installed skill plus the registered MCP/CLI. No extra coaching. |
| Give a realistic task. Do not lead. | Give a realistic task: "set it up", "ingest this", "find what it says about X", "put the spec on a canvas". |
| Observe hesitation and error. | Read the transcript. Note dead-ends, wrong turns, and false conclusions. |
| Run a think-aloud protocol. | The agent's visible reasoning is the think-aloud. It comes for free. |
| Rate severity. | Rate severity by blast radius. A silently false signal is worse than a dead-end, which is worse than an extra round-trip. |

The agent narrates its own near-misses. That is the advantage over UX testing. A
subject will tell you, in words, "the skill listed no search tool, so my first
instinct was to answer 'no search exists', which would have been false."

## The cardinal AX failure: a surface that lies

The dominant failure AX testing surfaces is **contract inconsistency**. An
agent-facing surface tells the agent something untrue. A human cross-checks a
tool against the world. An agent trusts the contract. So false confidence is the
cardinal AX sin, and **contract truth matters more than features**.

The principle, in one test subject's words: "I can work around a missing flag. I
can't safely work around a tool that tells me something false."

## AX heuristics (a starting set)

These are the agent analog of Nielsen's usability heuristics.

1. **Contract truth.** Every surface agrees. The skill, the tool list, the
   command output, and any verdict describe the same reality.
2. **Pure machine output.** `stdout` is parseable. Logs, progress, and chatter
   go to `stderr`. Errors are structured objects with a code and a hint, never a
   raw traceback.
3. **Single-round-trip sufficiency.** A result carries what the agent needs to
   act and to cite, without a follow-up call. A search hit includes the text and
   the page and the bbox.
4. **Honest verdicts.** A gate fails only when the real operation would fail. A
   check that cries wolf is worse than no check.
5. **Discoverability from the skill alone.** An agent reading only the skill can
   find the capability. A real tool that the skill omits does not exist, as far
   as the agent is concerned.
6. **Self-correcting, legible errors.** The tool repairs bad input where it can,
   and explains what to do when it cannot.

## Worked example: one ANCHOR AX-test session

A fresh agent was asked to set up ANCHOR with a personal key, ingest a PDF, and
find content in it. It succeeded at the task. It also produced these findings.

| Finding | Heuristic violated | Severity | Status |
| --- | --- | --- | --- |
| The skill listed `get_gold_regions` but no search tool, so the agent nearly told the user "no search exists." Search exists across CLI, MCP, and HTTP. | Discoverability, Contract truth | High (false "no") | Fixed: `search_documents` / `anchor search` now in the skill. |
| `anchor check --probe` reported "not ready" while the real ingest worked. The probe sent a deprecated `max_tokens` the model rejected. Ingestion sends neither token param. | Honest verdicts | High (corrosive false negative) | Fixed: the probe sends no token-cap parameter. |
| `anchor ingest` mixed RapidOCR INFO logs and progress bars into the output. | Pure machine output | Medium (a stricter parser would choke) | Fixed: `stdout` is pure JSON, noise quieted to `stderr`. |
| `anchor init` echoed the resolved config back, including key state. The agent could set up and know it was set up. | (Positive) Contract truth | n/a | Keep. The model for the rest of the CLI. |

The through-line: skill ≠ CLI, probe ≠ ingest, logs ≠ stdout. Three instances of
one bug. The fix was not a feature. It was making each surface tell the truth.

## How to run an AX test on ANCHOR

1. Pick a task a real user would ask for. Keep it end to end.
2. Start a fresh agent session in a clean folder. Give it the installed skill and
   the registered MCP or CLI, and nothing else. Do not coach it.
3. Give the task in one message. Then read, do not help.
4. Log each friction against the heuristics above, with a severity.
5. Fix contract inconsistencies first. Add a regression test so the surface
   cannot drift back. Then improve ergonomics.
6. Re-run the task to confirm the friction is gone.

## Next tier: ergonomics after truth

Once the surfaces tell the truth, AX work shifts from correctness to ergonomics.
The open item for ANCHOR is a cite-ready search result: `anchor search --json`
(and the matching MCP shape) returning, inline per hit, the full region text,
the page, the bbox, the `region_id`, a section breadcrumb, and optional
neighbors. That lets an agent answer and cite in a single call, which is
heuristic 3 in practice.
