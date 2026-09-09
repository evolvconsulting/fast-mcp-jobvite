"""The HTTP transport's hardening: auth, scopes, middleware, request id.

U9. **No §8 case owns this unit** - `IMPLEMENTATION-PLAN.md` §U9 says so
in as many words, and adds that *"nothing in the coupling gate will miss
them if they are dropped."* Every other unit here has a required case
that fails when its behaviour goes; this one does not. A silently
deleted test in this module leaves every gate green, which is why every
behaviour below has an amputation row proved able to fail rather than a
mutation of a constant.

**Why this is a module and not more of `server.py`.** `server.py` builds
the instance and its lifespan for BOTH transports. Everything here is
conditional on `http`, and keeping it separate makes "this code does not
run on stdio" a property of an import rather than of a branch a reader
has to trace.

**stdio is unauthenticated by design** (DESIGN.md:917-921): anything
able to spawn the process may call every tool, and the trust boundary is
the operating system's. That is not a gap this module closes - it is the
reason `require_scopes` is applied only when the transport is `http`.
`_RequireScopes` denies an ABSENT token, so applying it on stdio would
remove every tool from a transport the design says is fully authorised.

**The five NOT-adopted middleware** - `ResponseCaching`,
`ErrorHandling`, `ResponseLimiting`, `Retry`, `Ping` - are each
excluded for a measured
reason (ADR-0004, DESIGN.md's *"Not used"* paragraph), and re-adding one
is a silent regression. Their absence is asserted, and the assertion is
worth nothing on its own: five absences measured against a stack nobody
proved non-empty cannot tell *excluded* from *no middleware at all*. The
positive control is `test_http_hardening.py`'s assertion that the three
ADOPTED middleware are present and that `StructuredLoggingMiddleware`
carries `include_payloads=False`, which is threat row C2-I1's value.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

from fastmcp import FastMCP
from fastmcp.server.auth import require_scopes
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.server.dependencies import get_access_token, get_http_headers
from fastmcp.server.middleware.logging import StructuredLoggingMiddleware
from fastmcp.server.middleware.middleware import (
    CallNext,
    Middleware,
    MiddlewareContext,
)
from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware
from fastmcp.server.middleware.timing import TimingMiddleware
from fastmcp.tools.base import Tool

# The name `fastmcp` itself uses for this type
# (`server/mixins/transport.py:15`), aliased on import for the same
# reason it aliases it: an unqualified `Middleware` in this module
# already means the MCP-protocol one, and the whole of ADR-0029's
# correction is that the two are different layers.
from starlette.middleware import Middleware as ASGIMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .audit import resolve_request_id
from .config import (
    CREATE_CANDIDATE,
    GET_CANDIDATE,
    GET_JOB_FEED,
    KNOWN_TOOLS,
    SEARCH_CANDIDATES,
    SEARCH_JOBS,
    Settings,
    is_loopback,
)
from .errors import VALIDATION_ERROR, build_problem
from .utils.correlation import request_id_scope

#: The three data classes of DESIGN.md §4.1, which DESIGN.md:901-902
#: also writes out as the token map's example scope list. The scope
#: names are the design's, not invented here - B15's lesson is that
#: guessing a name that happens to match is still guessing.
SCOPE_CANDIDATES: Final = "candidates:read"
SCOPE_JOBS: Final = "jobs:read"
SCOPE_FEED: Final = "feed:read"

#: Every tool, mapped to the data class it reads. **Keyed on the
#: container, not on a hand-kept list**: `_assert_total` below asserts
#: this map's key set is EQUAL to `KNOWN_TOOLS`, so a tool added to
#: `config.py` without a scope here fails at import rather than
#: registering unscoped. A hand-kept list beside its container is blind
#: to the member nobody added, and that is the shape this project has
#: measured most often.
#:
#: `create_candidate` writes candidate records, so it holds the
#: candidate-PII class. DESIGN.md:906-908 records that the earlier axis
#: - "a read-only token never sees the write tool" - COLLAPSED whenever
#: the write was out of scope, and that the surviving axis is the data
#: class. On stdio the write rests on the deploy-time flag plus
#: approval rather than on this scope (DESIGN.md:919-921).
TOOL_SCOPES: Final[dict[str, str]] = {
    SEARCH_CANDIDATES: SCOPE_CANDIDATES,
    GET_CANDIDATE: SCOPE_CANDIDATES,
    CREATE_CANDIDATE: SCOPE_CANDIDATES,
    SEARCH_JOBS: SCOPE_JOBS,
    GET_JOB_FEED: SCOPE_FEED,
}


def _assert_total() -> None:
    """Refuse to import with a tool that has no data class.

    Raises:
        RuntimeError: If `TOOL_SCOPES` and `KNOWN_TOOLS` differ in
            either direction. Both directions matter: a missing key is
            an unscoped tool, and an extra key is a scope nothing
            enforces.
    """
    if frozenset(TOOL_SCOPES) != KNOWN_TOOLS:
        unscoped = sorted(KNOWN_TOOLS - frozenset(TOOL_SCOPES))
        unknown = sorted(frozenset(TOOL_SCOPES) - KNOWN_TOOLS)
        msg = (
            f"TOOL_SCOPES must cover exactly KNOWN_TOOLS; "
            f"unscoped={unscoped} unknown={unknown}"
        )
        raise RuntimeError(msg)


_assert_total()

#: Requests per second the inbound limiter sustains, and the burst it
#: allows. **No environment variable declares these**: DESIGN.md's
#: variable set is closed at fifteen and none of them is an inbound
#: rate, so these are module constants rather than a sixteenth variable
#: invented here (B15).
#:
#: **`+ 2` is FastMCP's own client's connect sequence, not a protocol
#: constant** (DESIGN.md:414-422). The limiter counts every MCP request,
#: not just tool calls, and the two are `server/discover` plus
#: `tools/list`. **A client whose connect sequence is heavier burns
#: more, and this sizing then UNDER-PROVISIONS and refuses real tool
#: calls.** No client but FastMCP's has ever been measured. Nothing in
#: this file measures it either - the constant is carried from the
#: design, not established here.
DESIRED_TOOL_CALLS_PER_BURST: Final = 10
INBOUND_BURST_CAPACITY: Final = DESIRED_TOOL_CALLS_PER_BURST + 2
#: This module's own claim to a coverage role from DESIGN.md:1443-1445,
#: read by `docs/reviews/check-coverage-floors.py`. The design names the
#: roles and not the paths, and the claim lives HERE rather than in a
#: role-to-module map in the checker, which would be a hand-kept list
#: beside its container. The checker asserts the two sets are EQUAL.
COVERAGE_ROLE: Final = "auth"

INBOUND_MAX_REQUESTS_PER_SECOND: Final = 5.0

#: The `client_id` a caller with no access token is billed to. stdio has
#: no token and thus no client id, but it has exactly one caller, so one
#: bucket is correct there. **DESIGN.md:432-435 calls that REASONING,
#: not measurement** - every limiter arm was run in-memory or over HTTP
#: and the limiter has never been exercised on stdio at all.
ANONYMOUS_CLIENT_ID: Final = "anonymous"

#: The canonical inbound correlation header
#: (`ai/tool-calling.md:173-175`). `get_http_headers` lower-cases every
#: name, so the lookup is lower-case and the constant is not.
REQUEST_ID_HEADER: Final = "X-Request-ID"

#: The middleware classes that must NEVER appear in the stack, each
#: excluded for a measured reason (ADR-0004 and DESIGN.md's *"Not
#: used"* paragraph). Named as strings rather than imported, because
#: importing a module in order to prove we do not use it is the one
#: import a linter is entitled to delete.
EXCLUDED_MIDDLEWARE: Final[frozenset[str]] = frozenset(
    {
        "ResponseCachingMiddleware",
        "ErrorHandlingMiddleware",
        "ResponseLimitingMiddleware",
        "RetryMiddleware",
        "PingMiddleware",
    }
)

#: DESIGN.md:165's *"Max total request body size - 1 MiB"*, at the
#: layer that row names.
#:
#: **THIS IS NOT `constraints.MAX_PAYLOAD_BYTES` AND IT IS NOT IMPORTED
#: FROM IT.** The two constants hold the same number off the same design
#: row and bound two different things, which is the whole of ADR-0029:
#: `MAX_PAYLOAD_BYTES` bounds the *serialised argument payload* on both
#: transports, and this bounds the *HTTP request body* on the HTTP
#: transport. Importing one into the other would say in code that they
#: are one control, and they are not - deleting either leaves a real
#: hole. `tests/test_arguments_sweep.py` pins both to the literal
#: `DESIGN.md:162-165` writes down, which is the one place the design's
#: number and the code's constants are joined.
#:
#: **This one is byte-exact and `MAX_PAYLOAD_BYTES` is not** (R8-M2).
#: That module re-serialises with `json.dumps(..., ensure_ascii=False)`
#: and so under-measures a `\u`-escaping client by up to 6x. Nothing is
#: re-serialised here: the number compared is either the caller's own
#: `Content-Length` or a running sum of the bytes ASGI actually
#: delivered. The residue R8-M2 records is now bounded at the layer that
#: can see the bytes, which is what that note asked for.
MAX_REQUEST_BODY_BYTES: Final = 1024 * 1024

#: The header the declared-length arm reads. ASGI lower-cases every
#: header name in `scope["headers"]`, and these are `bytes`, not `str`.
_CONTENT_LENGTH_HEADER: Final = b"content-length"


def token_client_id(token: str) -> str:
    """Return the non-secret client id a bearer token is billed to.

    **A digest, not the token.** `RateLimitingMiddleware` puts the
    client id into the text of the `MCPError` it raises on a trip
    (`rate_limiting.py:171`), and that error reaches the caller and the
    log. A raw bearer token there would publish a credential on the one
    path guaranteed to be hit by whoever is attacking the limiter.

    **Stable across restarts**, unlike an enumeration index: two
    processes reading the same `JOBVITE_HTTP_TOKENS` bill the same
    caller to the same id, so a log from one is joinable to a log from
    the other.

    Args:
        token: One bearer token from `JOBVITE_HTTP_TOKENS`.

    Returns:
        A 16-character hex digest of the token.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def build_token_verifier(settings: Settings) -> StaticTokenVerifier | None:
    """Build the `StaticTokenVerifier` from `JOBVITE_HTTP_TOKENS`.

    **Returns `None` on stdio, which is not the same as an empty
    verifier.** DESIGN.md:917-921 makes stdio unauthenticated by design;
    a verifier holding no tokens would refuse every call on a transport
    the design says is fully authorised.

    **This never refuses.** Every refusal for this variable already
    happened in `config.validate_settings` - unset, malformed JSON, an
    empty token key, an empty scope list - so reaching here with an
    unusable value is a programming error rather than an operator's
    input. `settings.http_tokens` being `None` while the transport is
    `http` therefore raises rather than quietly building an open server.

    Args:
        settings: Settings that have already passed
            `validate_settings`.

    Returns:
        The verifier, or `None` when the transport is not `http`.

    Raises:
        ValueError: If the transport is `http` and `http_tokens` is
            unset. `validate_settings` should have refused it.
    """
    if settings.mcp_transport != "http":
        return None
    if settings.http_tokens is None:
        msg = (
            "JOBVITE_MCP_TRANSPORT=http requires JOBVITE_HTTP_TOKENS; "
            "validate_settings should have refused this configuration"
        )
        raise ValueError(msg)
    parsed: dict[str, list[str]] = json.loads(settings.http_tokens.get_secret_value())
    return StaticTokenVerifier(
        tokens={
            token: {"client_id": token_client_id(token), "scopes": list(scopes)}
            for token, scopes in parsed.items()
        }
    )


def rate_limit_client_id(context: MiddlewareContext[Any]) -> str:
    """Return the bucket a request is billed to.

    **This function is the whole point of the limiter being adopted at
    all.** `RateLimitingMiddleware`'s `get_client_id` is optional, and
    with it unset `_get_client_identifier` returns the literal string
    `"global"` (`rate_limiting.py:157`) despite the docstring implying
    per-client. One noisy integrator would then throttle everyone,
    which is DESIGN.md:411-413's first constraint and the defect the
    per-client test exists for.

    Args:
        context: The middleware context, unused. The identity comes
            from the access token in the request's own context, which
            is where FastMCP puts it; the parameter is part of the
            framework's callback signature.

    Returns:
        The token's `client_id`, or `ANONYMOUS_CLIENT_ID` where there
        is no token.
    """
    del context
    token = get_access_token()
    if token is None:
        return ANONYMOUS_CLIENT_ID
    return token.client_id


class RequestIdMiddleware(Middleware):
    """Bind the request's correlation id for the whole request.

    **The transport half of `resolve_request_id`.** `audit.py` owns the
    validation - an inbound `X-Request-ID` is echoed only if it is a
    valid UUIDv4, and anything else is discarded and replaced (C7-T1,
    DESIGN.md:1895). Nothing reached that function from a header
    before this class: `get_http_headers` is the only place the header
    exists, and it is an HTTP-transport dependency.

    **A malformed id is REPLACED, not refused.** A bad correlation
    header is not a reason to fail a tool call. The failure it prevents
    is log forging: a value carrying a newline writes a second,
    attacker-authored line into the audit stream.

    On stdio `get_http_headers` returns an empty mapping, so the
    inbound id is `None` and a fresh one is minted - the same result
    the tools got before this middleware existed.
    """

    async def on_request(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:  # noqa: ANN401
        """Resolve and bind the correlation id, then run the request.

        Args:
            context: The middleware context.
            call_next: The rest of the chain.

        Returns:
            Whatever the rest of the chain returned.
        """
        inbound = get_http_headers().get(REQUEST_ID_HEADER.lower())
        with request_id_scope(resolve_request_id(inbound)):
            return await call_next(context)


def build_middleware(settings: Settings) -> list[Middleware]:
    """Build the middleware stack, outermost first.

    Three adopted, and the order is the order DESIGN.md §7.7 lists
    them. `RequestIdMiddleware` is ours and runs first so every log
    line the other two emit carries the correlation id.

    Args:
        settings: Settings that have already passed
            `validate_settings`.

    Returns:
        The stack. Identical on both transports except for the
        limiter's client id, which has no token to read on stdio.
    """
    del settings
    return [
        RequestIdMiddleware(),
        TimingMiddleware(),
        # `include_payloads=False` is C2-I1's value (DESIGN.md:1830)
        # and is passed EXPLICITLY. The framework's default is also
        # `False` today, so this keyword changes no behaviour right
        # now - it is here so that a framework default flipping, or
        # somebody flipping this, is a visible diff in our own source
        # rather than a dependency bump. ADR-0011 records what the
        # value costs: the middleware emits no arguments at all, so
        # `audit.py` emits redacted ones itself.
        StructuredLoggingMiddleware(include_payloads=False),
        RateLimitingMiddleware(
            max_requests_per_second=INBOUND_MAX_REQUESTS_PER_SECOND,
            burst_capacity=INBOUND_BURST_CAPACITY,
            # MANDATORY. See `rate_limit_client_id`.
            get_client_id=rate_limit_client_id,
        ),
    ]


def registered_tools(server: FastMCP[Any]) -> list[Tool]:
    """Return the live `Tool` objects registered on a server.

    **Private-API access, stated rather than hidden.** FastMCP's only
    public accessors - `list_tools` and `get_tool` - are coroutines,
    and `build_server` is synchronous by design (`server.py` builds
    before any loop exists). The objects here are the same objects
    those coroutines return; `test_http_hardening.py` asserts the scope
    it sets is visible through the public `list_tools`, so a rename of
    this attribute fails a test instead of silently scoping nothing.

    Args:
        server: The instance to read.

    Returns:
        Every registered tool, in registration order.
    """
    components = server._local_provider._components  # noqa: SLF001
    return [item for item in components.values() if isinstance(item, Tool)]


def apply_tool_scopes(server: FastMCP[Any], settings: Settings) -> None:
    """Put `require_scopes` on every registered tool, on HTTP only.

    **`require_scopes` removes an unauthorised tool from `tools/list`
    entirely, and a direct call returns "Unknown tool" rather than a
    permission error** (DESIGN.md:909-912). Good behaviour, confusing
    failure mode; the README documents it or every support conversation
    starts in the wrong place.

    **Not applied on stdio, and that is a design position rather than
    an optimisation.** `_RequireScopes.__call__` returns `False` for an
    absent token (`authorization.py:76-77`), and stdio has no token at
    all, so applying it there would hide every tool on the transport
    DESIGN.md:917-921 declares fully authorised.

    Args:
        server: The instance whose tools are already registered.
        settings: Settings that have already passed
            `validate_settings`.

    Raises:
        KeyError: If a registered tool has no entry in `TOOL_SCOPES`.
            `_assert_total` makes that unreachable from `config.py`'s
            names; a tool registered under some other name should fail
            loudly rather than serve unscoped.
    """
    if settings.mcp_transport != "http":
        return
    for tool in registered_tools(server):
        tool.auth = require_scopes(TOOL_SCOPES[tool.name])


class _BodyTooLarge(Exception):  # noqa: N818 - not an "Error"; it is a signal
    """Raised out of the wrapped `receive` when the running sum trips.

    **Deliberately not a `FastMcpJobviteError`.** That hierarchy is the
    tool layer's, and `problem_from_exception` maps it; this never
    reaches the tool layer and never reaches that mapper. It exists only
    to unwind the application out of an `await receive()` so the
    middleware below can answer instead, and it is caught by the one
    `except` that raised it.
    """


class BodySizeLimitMiddleware:
    """DESIGN.md:165's 1 MiB request-body cap, at the ASGI layer.

    **Why here and not `build_middleware`** (ADR-0029 as corrected).
    `build_middleware` returns `fastmcp` `Middleware` objects, which are
    MCP-*protocol* middleware: by the time one runs, the body has been
    read off the socket and parsed into a message. A cap there would
    bound nothing, because the bytes are already in memory. An
    `ASGIMiddleware` - which is `starlette.middleware.Middleware`, the
    type `FastMCP.http_app` and `run_http_async` both take - sits under
    that and sees `scope`, `receive` and `send`. It is the only layer in
    this server where a body can be refused before it is buffered.

    **Two arms, because a body can arrive two ways.**

    1. **`Content-Length` declared.** Refused on the header alone. The
       application is never called and not one byte of body is read.
    2. **No `Content-Length`** - `Transfer-Encoding: chunked`. There is
       no number to read, so `receive` is wrapped and the delivered
       bytes are summed as they arrive. The sum is compared on **every**
       chunk, so the refusal fires on the chunk that crosses the line
       and never after the whole body is held. **This is the arm an
       attacker uses**, because omitting the header is free and defeats
       any check that only reads it.

    A caller that lies - `Content-Length: 10` followed by a megabyte -
    is caught by arm 2, which runs regardless of what arm 1 read. The
    two are not alternatives; arm 1 is an early exit and arm 2 is the
    bound.

    **What the caller gets, and why that row.**
    `/problems/validation-error`, **422**, built by `build_problem` like
    every other problem object in this server.

    ADR-0029 declined to pick between 413 and 422 and left the choice to
    this unit. **413 is not available.** `errors.py`'s registry is
    closed - "every entry is a verbatim row of `error-contract.md`;
    nothing here is minted locally" - and that table has **no 413 row**
    at all. Choosing 413 means minting `/problems/payload-too-large`,
    and DESIGN.md:561-562 makes a published `type` URI a contract owed
    forever, which is exactly the invention the registry is closed
    against. ADR-0031 already ruled this once, for the refused-approval
    condition: **add the row's use, not a new slug.**

    422 is also the right answer on the merits rather than merely the
    available one. `error-contract.md`'s own "When" column for that row
    reads *"Request body/params failed validation"*, and an oversized
    body is the fourth row of the same §2.1 table whose other three are
    validation failures. DESIGN.md:186-188 reached the same number from
    the other side: it corrects an earlier revision that said `400` with
    *"had one done so its status would be 422, not 400, per the registry
    mapping in §5.1"*.

    **The cost of 422, stated rather than glossed:** 413 is the more
    precise HTTP status, and a client reading only the status line loses
    the signal that the problem was size. That signal is in `detail`,
    which names the limit and what was received - the load-bearing role
    ADR-0031 gave `detail` for the same reason.

    **Why a problem object at all, when §2.1's other three limits
    produce none.** DESIGN.md:181-190 is about checks *in the input
    models*, which run pre-dispatch and are *raised* by the framework -
    §5.1's third exception. This middleware is on the other side of that
    boundary: it is an HTTP layer holding `send`, so it *returns* a
    response, which is the property §5.1 says makes a problem object
    safe. The §8 #9 argument arms still assert `ValidationError` and are
    still right to; this arm asserts a problem shape and is not in
    tension with them.

    **HTTP only, by construction.** Nothing constructs this on stdio -
    it is reachable only through `http_run_kwargs`, which
    `__main__.py` calls only for `transport="http"`. There is no request
    body on stdio, so this cap bounds nothing there and
    `constraints.MAX_PAYLOAD_BYTES` remains the only inbound bound on
    that path. **The two are not duplicates.**

    Attributes:
        app: The ASGI application this wraps.
        max_bytes: The ceiling, in bytes. A body of exactly this size is
            ACCEPTED; one byte more is refused.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int = MAX_REQUEST_BODY_BYTES,
    ) -> None:
        """Wrap `app` with a ceiling on the request body.

        Args:
            app: The ASGI application to wrap. Starlette constructs this
                positionally, which is why it is the first parameter.
            max_bytes: The ceiling. Defaulted rather than required so
                that the default is the design's number and a test that
                wants a small one has to say so out loud.
        """
        self.app = app
        self.max_bytes = max_bytes

    def _declared_length(self, scope: Scope) -> int | None:
        """Return the request's `Content-Length`, or `None`.

        `None` covers three cases that are all handled the same way -
        the header is absent, it is not an integer, or it is negative -
        because every one of them means *there is no trustworthy
        declared size*, and the streaming bound is what answers that.
        Refusing here on a malformed header would be this module
        deciding framing validity, which is the transport's job.

        Args:
            scope: The ASGI connection scope.

        Returns:
            The declared length when there is a usable one.
        """
        for name, value in scope.get("headers", []):
            if name.lower() != _CONTENT_LENGTH_HEADER:
                continue
            try:
                declared = int(value)
            except (TypeError, ValueError):
                return None
            return declared if declared >= 0 else None
        return None

    def _problem_response(self, scope: Scope, received: str) -> bytes:
        """Build the 422 body for a refusal, as JSON bytes.

        The correlation id comes from the caller's `X-Request-ID` by way
        of `resolve_request_id`, so a refusal joins to the caller's own
        logs exactly as a tool call does. `RequestIdMiddleware` cannot
        do it for us: it is MCP-protocol middleware and never runs,
        because this refusal happens before any message is parsed.

        Args:
            scope: The ASGI connection scope, for the inbound header.
            received: How much arrived, phrased for `detail`.

        Returns:
            The serialised problem object.
        """
        wanted = REQUEST_ID_HEADER.lower().encode()
        inbound: str | None = None
        for name, value in scope.get("headers", []):
            if name.lower() == wanted:
                inbound = value.decode("latin-1")
                break
        problem = build_problem(
            VALIDATION_ERROR,
            (
                f"request body is larger than {self.max_bytes} bytes "
                f"(DESIGN.md:165); {received}"
            ),
            resolve_request_id(inbound),
        )
        return json.dumps(problem).encode()

    async def _refuse(
        self,
        scope: Scope,
        send: Send,
        received: str,
    ) -> None:
        """Send the 422 problem response and read nothing further.

        `application/problem+json` is `error-contract.md:44`'s required
        media type on every error response, and is set here explicitly
        rather than left to a framework default this response never
        reaches.

        Args:
            scope: The ASGI connection scope.
            send: The ASGI send callable.
            received: How much arrived, phrased for `detail`.
        """
        body = self._problem_response(scope, received)
        await send(
            {
                "type": "http.response.start",
                "status": VALIDATION_ERROR.status,
                "headers": [
                    (b"content-type", b"application/problem+json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Bound the request body, then hand off to the application.

        Args:
            scope: The ASGI connection scope.
            receive: The ASGI receive callable.
            send: The ASGI send callable.

        Raises:
            _BodyTooLarge: Re-raised in the one case this cannot answer
                - the application had already begun a response when the
                bound tripped, so there is no status line left to write.
                Letting it propagate closes the connection, which is a
                worse outcome than a 422 and a better one than a
                half-written response claiming success.
        """
        if scope["type"] != "http":
            # Lifespan and websocket scopes have no request body. A cap
            # that "handled" them would be inoperative code.
            await self.app(scope, receive, send)
            return

        # --- arm 1: the declared length, read before any body ---------
        declared = self._declared_length(scope)
        if declared is not None and declared > self.max_bytes:
            await self._refuse(scope, send, f"Content-Length declared {declared} bytes")
            return

        # --- arm 2: the running bound on what actually arrives --------
        # Runs even when arm 1 passed, because arm 1 believed a number
        # the caller chose.
        seen = 0
        response_started = False

        async def counting_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    raise _BodyTooLarge
            return message

        async def watching_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, watching_send)
        except _BodyTooLarge:
            if response_started:
                raise
            await self._refuse(scope, send, f"received over {self.max_bytes} bytes")


def http_run_kwargs(settings: Settings) -> dict[str, Any]:
    """Return the keyword arguments `mcp.run(transport="http")` takes.

    **`allowed_hosts` and `allowed_origins` are SET whenever the bind
    is not loopback**, rather than left at the framework default. They
    address DNS-rebinding and browser-origin confusion; they do nothing
    about plaintext, which is why `config._check_transport` refuses an
    off-loopback bind without a declared TLS proxy as a separate
    refusal.

    `allowed_origins` is set to the EMPTY list, not omitted. The
    framework distinguishes the two: `allowed_origins is not None` is
    what sets `has_explicit_allowed_origins` (`server/http.py:242`), so
    `[]` means *no browser origin is trusted* while `None` means *use
    the default*. Empty is the fail-closed value for a server no
    browser is meant to reach.

    On loopback both are omitted deliberately: the framework's own
    default already admits the loopback names, and narrowing it here
    would break `localhost` against a `127.0.0.1` bind for no threat
    that exists inside the host.

    Args:
        settings: Settings that have already passed
            `validate_settings`.

    **`middleware` is ALWAYS set, and on loopback too.** It carries
    `BodySizeLimitMiddleware`, which is DESIGN.md:165's body cap
    (ADR-0029 as corrected). Unlike `allowed_hosts`, this is not a
    rebinding control that loopback makes moot: anything that can open a
    socket to this server can send it an unbounded body, and on loopback
    that set is every process on the host. `starlette.middleware.
    Middleware` is what `run_http_async` means by `ASGIMiddleware`, and
    it defers construction, so the class and its keyword go in and the
    framework instantiates it around the app.

    Returns:
        `host`, `port` and `middleware` always; `allowed_hosts` and
        `allowed_origins` only off loopback.
    """
    kwargs: dict[str, Any] = {
        "host": settings.mcp_host,
        "port": settings.mcp_port,
        "middleware": [
            ASGIMiddleware(
                BodySizeLimitMiddleware,
                max_bytes=MAX_REQUEST_BODY_BYTES,
            )
        ],
    }
    if not is_loopback(settings.mcp_host):
        host = settings.mcp_host
        kwargs["allowed_hosts"] = [host, f"{host}:{settings.mcp_port}"]
        kwargs["allowed_origins"] = []
    return kwargs


__all__ = [
    "ANONYMOUS_CLIENT_ID",
    "DESIRED_TOOL_CALLS_PER_BURST",
    "EXCLUDED_MIDDLEWARE",
    "INBOUND_BURST_CAPACITY",
    "INBOUND_MAX_REQUESTS_PER_SECOND",
    "MAX_REQUEST_BODY_BYTES",
    "REQUEST_ID_HEADER",
    "SCOPE_CANDIDATES",
    "SCOPE_FEED",
    "SCOPE_JOBS",
    "TOOL_SCOPES",
    "BodySizeLimitMiddleware",
    "RequestIdMiddleware",
    "apply_tool_scopes",
    "build_middleware",
    "build_token_verifier",
    "http_run_kwargs",
    "rate_limit_client_id",
    "registered_tools",
    "token_client_id",
]
