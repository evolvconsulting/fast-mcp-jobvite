# ADR-0036: fastmcp 4.0.3, the GA line, replaces the 4.0.0b4 beta

**Status:** Accepted (JACK as Tier 0 of the fast-mcp lane, 2026-09-08, under Phil's directive of 2026-09-08 to move every fast-mcp project to the latest fastmcp; KING concurred, K-0060). Proposed by suborch-jobvite-403 the same day, which measured it and did not decide it.
**Type:** Design change

## Context

`docs/DESIGN.md` is frozen at `d1f1a52`. Three clauses of it, and one earlier ADR, pin the beta:

- `DESIGN.md:1485` - *"Python `>=3.12`. `fastmcp==4.0.0b4` targeting the sessionless `2026-07-28`
  spec as deliberate early adopters."*
- `DESIGN.md:1497-1506` - the packaging block stated **verbatim**, carrying `"fastmcp==4.0.0b4"`,
  `"fastmcp-slim==4.0.0b4"`, `"mcp==2.1.1"` and `[tool.uv] prerelease = "explicit"`.
- `DESIGN.md:1518-1520` - *"`--prerelease=allow` is global in uv and pulls in a beta pydantic;
  `explicit` alone fails to resolve because `fastmcp-slim` arrives transitively. Naming it
  directly resolves pydantic to stable."*
- `ADR-0001` Decision - *"Pin `fastmcp==4.0.0b4` and target the sessionless `2026-07-28` spec."*

The 4.0 line has since shipped. PyPI upload times, read from the JSON API on 2026-09-08:

| release | uploaded |
|---|---|
| 4.0.0b4 | 2026-08-26T22:59:04Z |
| 4.0.0 (GA) | 2026-08-31T18:20:31Z |
| 4.0.1 | 2026-09-02T00:20:45Z |
| 4.0.2 | 2026-09-02T23:28:03Z |
| 4.0.3 | 2026-09-05T00:31:33Z |

So `DESIGN.md:1485`'s *"deliberate early adopters"* now describes running a superseded beta of a
released line, which is a different and worse position than the one Phil actually chose. The
design did not become wrong; the world moved underneath a sentence that was right when written.

## The measurement that settles the `fastmcp-slim` half

`DESIGN.md:1518-1520` and `pyproject.toml`'s comment both assert the `fastmcp-slim` pin is
load-bearing. `tests/test_manifest.py::test_removing_fastmcp_slim_breaks_the_resolve` was the
control, and its own failure message names this ADR as the remedy:

> *"removing the fastmcp-slim pin STILL resolved. Either uv's behaviour changed or the pin is no
> longer load-bearing; DESIGN.md:1499-1501 needs an ADR before the line is touched."*

Five real `uv lock` resolves, each in its own scratch directory, none of them in the worktree:

| arm | manifest | rc | packages | fastmcp-slim resolved to |
|---|---|---|---|---|
| 1 | as committed (4.0.0b4, slim named) - **positive control** | 0 | 121 | 4.0.0b4 |
| 2 | 4.0.3, slim still named | 0 | 121 | 4.0.3 |
| 3 | 4.0.3, slim line **dropped** | 0 | 121 | 4.0.3 |
| 4 | 4.0.3, slim dropped and `[tool.uv]` removed | 0 | 121 | 4.0.3 |
| 5 | 4.0.0b4, slim line **dropped** - **negative control** | 1 | 0 | resolve failed |

Arm 5's verbatim output:

    Because there is no version of fastmcp-slim[client]==4.0.0b4 and
    fastmcp==4.0.0b4 depends on fastmcp-slim[client]==4.0.0b4, we can
    conclude that fastmcp==4.0.0b4 cannot be used.

Both controls fire. The pin **was** load-bearing and **is not** at a GA pin, because
`prerelease = "explicit"` refuses a transitive PRERELEASE nobody named, and 4.0.3 is not one.
Arm 3 is what the old control asserts the negative of, so that control cannot survive the bump
in place: after the bump the mutation it applies resolves, and it would go green by testing
nothing.

## Decision

1. Pin `fastmcp==4.0.3`.
2. Drop the explicit `fastmcp-slim` line. A pin whose only justification is a comment that has
   become false is worse than no pin: the next reader trusts the comment.
3. **Keep `mcp==2.1.1` pinned explicitly.** `DESIGN.md:1486-1488`'s reason is untouched by the GA
   move - the `ResponseLimiting` regression arrived through the transitive SDK with zero change
   to the code that broke. Measured: `mcp` and `mcp-types` stay at 2.1.1 across the bump.
4. **Keep `[tool.uv] prerelease = "explicit"`.** Arm 4 shows the resolve no longer needs it, which
   is exactly why it should stay: it costs nothing and it is what stops a future prerelease
   arriving unannounced. `test_prerelease_is_explicit` read it out of the manifest and could not
   tell a live setting from an inert one; the replacement network arm now runs it.
5. **`ADR-0001` stands as the record of what was decided when.** This ADR amends its version pin
   only. Its spec target (`2026-07-28`, sessionless), its explicit `mcp` pin, and its
   characterise-and-report-upstream posture are unchanged.
6. `docs/DESIGN.md` is **not edited**. This ADR is the instrument that changes it, and
   `docs/adr/README.md` records the amendment edge.

## Consequences

**Two controls change, and neither is deleted without a replacement.**

- `test_removing_fastmcp_slim_breaks_the_resolve` is replaced by
  `test_a_prerelease_pin_without_its_transitive_still_fails`. Same mechanism, same `network`
  marker, same matched pair with its positive control, so `ci.yml`'s network floor of 2 is
  unchanged. The fixture is the real 4.0.0b4 that made the rule, so the arm keeps firing.
- `test_the_fastmcp_slim_justification_comment_survives` is renamed to
  `test_the_absent_slim_pin_justification_comment_survives` and guards the comment that records
  **why the line is absent** - the half a reader cannot recover from a manifest, since a deleted
  line leaves no trace of the decision that deleted it. `scripts/check-u0-test-controls.sh`'s row
  moves with it, so the harness still mutates a string that exists.

**What this does not buy.** No behaviour of ours changes. The bump moves exactly two packages
(`fastmcp`, `fastmcp-slim`), holds 121 packages either side, and every other pinned version is
byte-identical. The 3-to-4 upgrade guide's removals were audited against the source, the tests,
the probes and the scripts and none of them is reachable from this code.

**The residual risk moves in our favour and should be said plainly.** `DESIGN.md:2009` rates
*"we run third-party code in the same process as the Jobvite credential, on a deliberately beta
stack"* as Medium on a Low likelihood judgement it calls contestable. A GA line does not remove
that risk; it removes the *beta* qualifier from it, which is the part the rating found hardest to
defend.

**What is NOT re-verified.** Every `[FROM SOURCE]` listing in `docs/research/FASTMCP.md` was
enumerated on 4.0.0b4 and has not been re-enumerated on 4.0.3. Each still names the version it
was read at; that document now says so at the top rather than implying currency.
