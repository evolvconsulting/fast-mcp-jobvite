# mypy: allow-untyped-defs, allow-untyped-calls
# ^ This file is a PROBE: its helpers build throwaway clients and
#   responders whose only caller is the arms below. mypy READS it -
#   that is the point of putting docs/reviews in `files` - and every
#   other strict check applies; only the two annotation knobs the ruff
#   per-file-ignores entry already relaxes for ANN are relaxed here, so
#   the two tools say the same thing about the same population.
"""R6 probe: does the `Retry-After` clamp sleep out the WHOLE budget?

`_wait_for_retry` clamps the wait to `max(remaining, 0.0)`. When Jobvite
asks for longer than the budget has left, the clamp makes us sleep
exactly the remaining budget - and `_attempt`'s pre-attempt check then
refuses the attempt we slept for.

ARM 1  Retry-After far larger than the budget. Measure wall-clock
       from the call to the 503. If the clamp sleeps the budget out,
       elapsed is ~budget; if the loop stops at once, elapsed is ~0.
ARM 1c the same drive with NO Retry-After header, where the jittered
       backoff is small, so the run is short. Proves the harness
       times the call rather than something constant.
"""

from __future__ import annotations

import asyncio
import sys
import time

import httpx2

sys.path.insert(0, "src")

from fast_mcp_jobvite.errors import JobviteUnavailableError  # noqa: E402
from fast_mcp_jobvite.services import jobvite_client as jc  # noqa: E402

BUDGET = 1.0


class _Secret:
    def __init__(self, value: str) -> None:
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


def client(handler, **kw):
    return jc.JobviteClient(
        api_key=_Secret("k"),
        api_secret=_Secret("s"),
        company_id=_Secret("c"),
        transport=httpx2.MockTransport(handler),
        **kw,
    )


def make(retry_after, status=503):
    async def handler(_req: httpx2.Request) -> httpx2.Response:
        headers = {"Retry-After": retry_after} if retry_after else {}
        body = b'{"status":{"code":%d}}' % status
        return httpx2.Response(status, content=body, headers=headers)

    return handler


async def arm(name, retry_after, status=503):
    jc.reset_breaker_for_test()
    c = client(make(retry_after, status), outbound_budget_seconds=BUDGET)
    # SEEDED, AND THE SEED IS THE POINT. Every handler this
    # probe installs returns 503 or 404, so an exception always
    # fires and `kind` was always bound - until it wasn't. Let a
    # future edit make the call SUCCEED and the unseeded version
    # raised `NameError: name 'kind' is not defined` at the print
    # below: a probe that crashes confusingly on the one outcome
    # that would be genuinely surprising. Found by CodeQL
    # (py/uninitialized-local-variable), not by any test -
    # nothing here exercises the success path, which is exactly
    # why it went unseen.
    kind = "NO EXCEPTION RAISED - the call SUCCEEDED, which this probe does not expect"
    t0 = time.monotonic()
    try:
        try:
            await c.request("GET", "/job")
        except JobviteUnavailableError as exc:
            kind = f"503 {type(exc).__name__}"
        except Exception as exc:  # noqa: BLE001
            kind = f"{type(exc).__name__}"
    finally:
        elapsed = time.monotonic() - t0
        await c.aclose()
    print(f"{name}: elapsed={elapsed:.2f}s  budget={BUDGET}s  outcome={kind}")
    return elapsed


async def main() -> None:
    ctl = await arm("ARM 0c 404, NOT retryable (real control)  ", None, 404)
    a = await arm("ARM 1c no Retry-After (jittered backoff) ", None)
    b = await arm("ARM 1  Retry-After: 900 (>> the budget)  ", "900")
    print()
    print(
        f"ARM 0c control: {ctl:.2f}s - a non-retryable call returns at once,"
        f" so the harness measures elapsed time and not a constant"
    )
    print(f"ARM 1c        : {a:.2f}s - the LOCAL backoff also burns the budget")
    burned = b >= BUDGET * 0.9
    print(
        f"ARM 1  verdict: {b:.2f}s -> "
        f"{'the clamp SLEEPS OUT the whole budget' if burned else 'stops early'}"
    )


asyncio.run(main())
