"""The `FastMCP` instance and lifespan composition (see below).

DESIGN.md:1033-1034 states "startup in order, teardown in strict
reverse, verified". That property had no test, and its two halves fail
differently: an out-of-order startup is usually visible, an out-of-order
teardown is usually not.
"""

from __future__ import annotations

import ast
import json
import pathlib
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.server.lifespan import Lifespan, lifespan
from pydantic import SecretStr

from fast_mcp_jobvite.__main__ import EXIT_CONFIGURATION_REFUSED, main
from fast_mcp_jobvite.config import READ_TOOLS, Settings, load_settings
from fast_mcp_jobvite.server import (
    build_server,
    create_server,
    make_base_lifespan,
)
from tests.test_arguments_sweep import INPUT_MODELS

V2 = {"JOBVITE_API_KEY": "k", "JOBVITE_API_SECRET": "s"}


@pytest.fixture
def clean_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> pytest.MonkeyPatch:
    """Remove every JOBVITE_ variable and move off any real `.env`."""
    import os

    for name in list(os.environ):
        if name.startswith("JOBVITE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    return monkeypatch


def _settings() -> Settings:
    return Settings(
        tools="search_jobs",
        api_key=SecretStr("k"),
        api_secret=SecretStr("s"),  # noqa: S106
    )


def test_mask_error_details_is_set_explicitly() -> None:
    """Never left to the framework default.

    Asserted on the built instance AND on the source, because a
    framework whose default happened to be True would satisfy the first
    alone - and the point of this case is that a dependency bump must
    not be able to change it silently.
    """
    server = build_server(_settings())
    assert server._mask_error_details is True
    source = (
        pathlib.Path(__file__).resolve().parents[1]
        / "src"
        / "fast_mcp_jobvite"
        / "server.py"
    ).read_text()

    # R3-L5. This was `assert "mask_error_details=True" in source`, a
    # substring match over raw text - which passes on a COMMENTED-OUT
    # line. That made the guard inoperative in precisely the scenario
    # the docstring above says it exists for: if a dependency bump
    # flipped the framework default to True, the instance assertion
    # would pass on the default and the source assertion would pass on a
    # comment, with the setting absent from the real call. Parse
    # instead, so only a live keyword argument counts.
    keywords = [
        keyword
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "mask_error_details"
    ]
    assert keywords, "server.py passes no mask_error_details keyword at all"
    assert all(
        isinstance(keyword.value, ast.Constant) and keyword.value.value is True
        for keyword in keywords
    ), "mask_error_details is passed, but not as a literal True"


async def test_composed_lifespans_start_in_order_and_tear_down_in_reverse() -> None:
    """DESIGN.md:1033-1034, which had no test before this one.

    Two composed lifespans, not one: with a single extra the sequence is
    up-then-down whatever the operator does, so a one-lifespan arm
    cannot tell "strict reverse" from "same order" and would pass
    against either.
    """
    order: list[str] = []

    def recorder(label: str) -> Lifespan:
        @lifespan
        async def _one(server: FastMCP[Any]) -> AsyncIterator[dict[str, Any]]:
            order.append(f"{label}-up")
            try:
                yield {label: True}
            finally:
                order.append(f"{label}-down")

        return _one

    server = build_server(_settings(), extra_lifespan=recorder("a") | recorder("b"))
    async with Client(server):
        pass

    assert order == ["a-up", "b-up", "b-down", "a-down"]


async def test_the_base_lifespan_publishes_the_settings() -> None:
    """Settings reach tools through the lifespan, not a global."""
    settings = _settings()
    server = build_server(settings)
    async with make_base_lifespan(settings)(server) as context:
        assert context["settings"] is settings
        assert context["enabled_tools"] == frozenset({"search_jobs"})


def test_create_server_builds_from_the_environment(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """The factory `fastmcp inspect` and `fastmcp run` point at."""
    for key, value in V2.items():
        clean_env.setenv(key, value)
    clean_env.setenv("JOBVITE_FEED_KEY", "fk")
    clean_env.setenv("JOBVITE_FEED_SECRET", "fs")
    clean_env.setenv("JOBVITE_COMPANY_ID", "c1")
    server = create_server()
    assert server._mask_error_details is True
    assert load_settings().enabled_tools == READ_TOOLS


def test_create_server_refuses_a_bad_environment(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """The refusal is not bypassed by going through the factory."""
    from fast_mcp_jobvite.config import ConfigurationError

    clean_env.setenv("JOBVITE_TOOLS", "not_a_tool")
    with pytest.raises(ConfigurationError):
        create_server()


def test_main_returns_the_refusal_status_without_serving(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """`main` returns on the refusal path, BEFORE `os._exit`.

    **The `build_server` stub is a safety interlock, not a mock, and it
    was added because the amputation harness needed it.** With the
    refusals amputated, this call falls through to
    `mcp.run(transport="http")` inside the pytest process and serves
    forever - a hang, not a failure, and one that took twenty-two
    minutes to be recognised as a hang rather than a slow run. The stub
    turns "the refusal did not fire" into a red test in the same second.
    Reaching it at all is the bug.
    """

    def _must_not_be_reached(*_args: object, **_kwargs: object) -> None:
        message = "main() got past the refusal and was about to serve"
        raise AssertionError(message)

    clean_env.setattr("fast_mcp_jobvite.__main__.build_server", _must_not_be_reached)
    clean_env.setenv("JOBVITE_MCP_TRANSPORT", "http")
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    for key, value in V2.items():
        clean_env.setenv(key, value)
    assert main() == EXIT_CONFIGURATION_REFUSED


async def test_the_server_registers_exactly_the_enabled_tools() -> None:
    """U1 owns the enable GATE, not the tools (DESIGN.md:992-1008).

    **Rewritten by U5, which is the unit that made the old assertion
    false.** It read `assert await client.list_tools() == []` under the
    name `test_the_server_registers_no_tool_yet`, and that was a true
    statement about a server with no tool modules rather than a
    property anyone wanted to keep - the moment a tool existed it had
    to change. What it was actually protecting is that registration
    goes through `settings.enabled_tools` and not around it, so that is
    what it asserts now, in both directions.

    The gate's own refusals are asserted in `test_config.py`; the
    tool's behaviour is asserted in `test_tools_jobs.py`. This case
    covers only the join between them, which is the part U1 owns.
    """
    settings = _settings()
    assert settings.enabled_tools == frozenset({"search_jobs"})
    server = build_server(settings)
    async with Client(server) as client:
        assert {tool.name for tool in await client.list_tools()} == {"search_jobs"}


async def test_a_server_with_no_enabled_tool_registers_nothing() -> None:
    """PAIRED with the case above: the gate can still say no.

    This is what survives of the original assertion, and it is the
    half worth keeping. A `register` that ignored
    `settings.enabled_tools` entirely would pass the case above and
    fail here, which is the only way to tell "registration honours the
    gate" from "registration happens to register the one tool that
    exists".

    **THE NAME CHANGED FROM `get_candidate` TO `create_candidate` WHEN
    U8 LANDED, and the rewrite is the point.** This case needs a tool
    that is DECLARED in `KNOWN_TOOLS` and has no `register` yet, so
    that naming it produces an empty server. `get_candidate` was that
    tool until U8 implemented it, at which point this assertion started
    testing the opposite of what its name says. `create_candidate` is
    U10's and is the remaining unimplemented read-shaped name.

    **This case therefore expires again when U10 lands**, which is a
    property of the case and not a defect: it is pinned to "a declared
    tool with no implementation", and the day there is none left, the
    gate has nothing to prove and the case should be deleted rather
    than repointed a third time.
    """
    settings = Settings(
        tools="create_candidate",
        api_key=SecretStr("k"),
        api_secret=SecretStr("s"),  # noqa: S106
    )
    server = build_server(settings)
    async with Client(server) as client:
        assert await client.list_tools() == []


@pytest.mark.asyncio
async def test_the_live_middleware_stack_is_five_and_the_fifth_is_injected() -> None:
    """ADR-0032: `build_middleware` returns four and FIVE run.

    `FastMCP.__init__` appends `DereferenceRefsMiddleware()` whenever
    `dereference_schemas` is true, which is its default. C2 was written
    against a stack that is not the one that runs; ADR-0032 ADOPTED the
    fifth rather than disabling it, so the threat model at
    `DESIGN.md:1822` now names all four - `Timing, StructuredLogging,
    RateLimiting, DereferenceRefs` - and carries its own row, C2-T2.
    This test is what keeps that heading honest about what runs.

    Asserting the WHOLE list rather than "the fifth is present": a
    membership check cannot see a sixth arriving, and a framework bump
    injecting one is precisely what this pins.
    """
    settings = Settings(
        tools="search_jobs",
        api_key=SecretStr("k"),
        api_secret=SecretStr("s"),  # noqa: S106
    )
    names = [type(m).__name__ for m in build_server(settings).middleware]
    assert names == [
        "RequestIdMiddleware",
        "TimingMiddleware",
        "StructuredLoggingMiddleware",
        "RateLimitingMiddleware",
        "DereferenceRefsMiddleware",
    ], f"the live stack changed: {names}"


def test_no_input_model_produces_a_ref_for_the_middleware_to_inline() -> None:
    """ADR-0032's tripwire, and its failure is a SIGNAL not a defect.

    `DereferenceRefsMiddleware` runs on every request and inlines `$ref`
    in published tool schemas. ADR-0032 rules its threat row low because
    it is a live NO-OP: measured, all five input models are flat, every
    field a bounded scalar, so there is nothing for it to inline.

    **The population is `test_arguments_sweep.INPUT_MODELS`, the ONE
    enumeration of the inbound surface (#90).** This file used to
    discover its own with `pkgutil` over `tools/` plus an
    `endswith("Input")` name filter - a second discovery of one set,
    and a name filter of the kind the sweep refuses by excluding output
    models on their `output_schema=` USE.

    **The swept set is a SUPERSET of what this claim is about, and that
    is deliberate.** ADR-0032 concerns what `DereferenceRefsMiddleware`
    rewrites, which is the published TOOL schema path; `ApprovalAnswer`
    reaches the host through `requested_schema=` and never through a
    tool schema. Asserting over the superset can raise a false alarm -
    and a false alarm here sends a reader to re-read ADR-0032's C2 row,
    which is the correct outcome. One shared container beats a
    correctly-scoped second one.

    **This reads the MODELS, which is the pre-middleware side, and the
    first version of this test read the published schemas instead - a
    control that could not fail.** The published side has no `$ref` by
    construction, because removing them is the middleware's entire job.
    Measured against a deliberately nested `SearchJobsInput`:

        MODEL      $ref count: 1
        PUBLISHED  $ref count: 0

    So a `$ref` count of zero read through a `Client` says nothing about
    whether the models nest. It reports the middleware working, which it
    would do either way.

    **That is a property of today's MODELS, not of the middleware.**
    `$ref` appears the moment any model nests - a sub-model, an enum,
    a discriminated union - and U14 landed a shared `InboundModel`
    base whose own tests already carry a `NestedProbe`.

    **So if this goes red, do not update the number.** It means
    ADR-0032's central fact has expired and its C2 row needs re-reading
    against a middleware that now rewrites what every caller sees.
    Nesting a model is fine; discovering it afterwards is not.
    """
    models = [(m.__name__, m) for m in INPUT_MODELS]
    assert len(models) >= 5, (
        f"found {len(models)} input models; the discovery is broken and a "
        "green here would mean nothing"
    )
    offenders = sorted(
        name
        for name, model in models
        if '"$ref"' in json.dumps(model.model_json_schema())
    )
    assert not offenders, (
        f"{offenders} now nest, so DereferenceRefsMiddleware is no longer a "
        "no-op. Re-read ADR-0032's C2 row rather than updating this test."
    )
