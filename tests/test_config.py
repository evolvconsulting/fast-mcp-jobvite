"""U1's configuration refusals (DESIGN.md:984-1029).

Every refusal case here is paired with a positive control, because a
guard that refuses everything is not a guard and its refusals prove
nothing (DESIGN.md:1451-1452).
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
from pydantic import SecretStr

from fast_mcp_jobvite.config import (
    CREATE_CANDIDATE,
    GET_CANDIDATE,
    GET_JOB_FEED,
    KNOWN_TOOLS,
    READ_TOOLS,
    SEARCH_CANDIDATES,
    SEARCH_JOBS,
    TOOL_REQUIREMENTS,
    ConfigurationError,
    Settings,
    is_loopback,
    load_settings,
    validate_settings,
)
from tests.conftest import ENV_EXAMPLE, REPO_ROOT

V2_PAIR = {"JOBVITE_API_KEY": "k", "JOBVITE_API_SECRET": "s"}
FEED_TRIPLE = {
    "JOBVITE_FEED_KEY": "fk",
    "JOBVITE_FEED_SECRET": "fs",
    "JOBVITE_COMPANY_ID": "c1",
}


@pytest.fixture
def clean_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> pytest.MonkeyPatch:
    """Remove every JOBVITE_ variable and move off any real `.env`.

    `Settings` reads `.env` from the working directory. Running in a
    fresh tmp_path is what makes "unset" mean unset rather than
    "whatever the developer happens to have".
    """
    import os

    for name in list(os.environ):
        if name.startswith("JOBVITE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    return monkeypatch


def _set(env: pytest.MonkeyPatch, mapping: dict[str, str]) -> None:
    for key, value in mapping.items():
        env.setenv(key, value)


# ----------------------------------------------------------------------
# The per-enabled-tool matrix, row by row, INCLUDING the negative
# (DESIGN.md:1011-1018).
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "required"),
    [
        (SEARCH_CANDIDATES, ("JOBVITE_API_KEY", "JOBVITE_API_SECRET")),
        (GET_CANDIDATE, ("JOBVITE_API_KEY", "JOBVITE_API_SECRET")),
        (SEARCH_JOBS, ("JOBVITE_API_KEY", "JOBVITE_API_SECRET")),
        (
            GET_JOB_FEED,
            ("JOBVITE_FEED_KEY", "JOBVITE_FEED_SECRET", "JOBVITE_COMPANY_ID"),
        ),
    ],
)
def test_each_row_of_the_matrix_refuses_each_of_its_own_variables(
    clean_env: pytest.MonkeyPatch, tool: str, required: tuple[str, ...]
) -> None:
    """Dropping a required variable of an enabled tool refuses boot."""
    supplied = dict(V2_PAIR) | dict(FEED_TRIPLE)
    for dropped in required:
        env = {k: v for k, v in supplied.items() if k != dropped}
        clean_env.setenv("JOBVITE_TOOLS", tool)
        for name in supplied:
            clean_env.delenv(name, raising=False)
        _set(clean_env, env)
        with pytest.raises(ConfigurationError) as excinfo:
            load_settings()
        assert dropped in str(excinfo.value)
        assert tool in str(excinfo.value)


@pytest.mark.parametrize(
    ("tool", "supplied"),
    [
        (SEARCH_CANDIDATES, V2_PAIR),
        (GET_CANDIDATE, V2_PAIR),
        (SEARCH_JOBS, V2_PAIR),
        (GET_JOB_FEED, FEED_TRIPLE),
    ],
)
def test_each_row_starts_when_its_own_variables_are_present(
    clean_env: pytest.MonkeyPatch, tool: str, supplied: dict[str, str]
) -> None:
    """The positive control for every row above."""
    clean_env.setenv("JOBVITE_TOOLS", tool)
    _set(clean_env, supplied)
    settings = load_settings()
    assert settings.enabled_tools == frozenset({tool})


def test_a_candidate_search_deployment_is_not_asked_for_a_company_id(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """The NEGATIVE of the matrix, stated at DESIGN.md:1010-1011.

    "a deployment using only candidate search must not be forced to
    invent a `companyId` it has no use for". A test that only ever adds
    variables passes against an implementation validating the union.
    """
    clean_env.setenv("JOBVITE_TOOLS", SEARCH_CANDIDATES)
    _set(clean_env, V2_PAIR)
    settings = load_settings()
    assert settings.company_id is None
    assert settings.missing_for(SEARCH_CANDIDATES) == []
    # And the union WOULD have been refused, so the assertion above is
    # not vacuously true of any configuration.
    assert settings.missing_for(GET_JOB_FEED) == [
        "JOBVITE_FEED_KEY",
        "JOBVITE_FEED_SECRET",
        "JOBVITE_COMPANY_ID",
    ]


# ----------------------------------------------------------------------
# JOBVITE_TOOLS (DESIGN.md:992-1008).
# ----------------------------------------------------------------------


def test_an_unrecognised_tool_name_is_a_startup_failure(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """DESIGN.md:1004-1005, not a silent skip."""
    clean_env.setenv("JOBVITE_TOOLS", "serch_jobs")
    _set(clean_env, V2_PAIR)
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()
    assert "serch_jobs" in str(excinfo.value)


def test_a_recognised_tool_name_starts(clean_env: pytest.MonkeyPatch) -> None:
    """The positive control for the case above."""
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    _set(clean_env, V2_PAIR)
    assert load_settings().enabled_tools == frozenset({SEARCH_JOBS})


def test_unset_tools_means_all_reads_and_never_the_write(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """DESIGN.md:994-996."""
    _set(clean_env, V2_PAIR | FEED_TRIPLE)
    assert load_settings().enabled_tools == READ_TOOLS


# ----------------------------------------------------------------------
# The ENABLE_WRITES / TOOLS conjunction, BOTH directions
# (DESIGN.md:998-1002).
# ----------------------------------------------------------------------


def test_enable_writes_true_with_tools_unset_does_not_register_the_write(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """DESIGN.md:1000-1001: the obvious step does nothing."""
    _set(clean_env, V2_PAIR | FEED_TRIPLE)
    clean_env.setenv("JOBVITE_ENABLE_WRITES", "true")
    settings = load_settings()
    assert CREATE_CANDIDATE not in settings.enabled_tools
    assert settings.enabled_tools == READ_TOOLS


def test_naming_the_write_without_the_flag_does_not_register_it(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """DESIGN.md:1002, the other direction."""
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs,create_candidate")
    _set(clean_env, V2_PAIR)
    settings = load_settings()
    assert CREATE_CANDIDATE not in settings.enabled_tools
    assert settings.enabled_tools == frozenset({SEARCH_JOBS})


def test_both_together_do_register_the_write(clean_env: pytest.MonkeyPatch) -> None:
    """The positive control: neither direction alone, both together."""
    clean_env.setenv("JOBVITE_TOOLS", "create_candidate")
    clean_env.setenv("JOBVITE_ENABLE_WRITES", "true")
    _set(clean_env, V2_PAIR)
    assert load_settings().enabled_tools == frozenset({CREATE_CANDIDATE})


# ----------------------------------------------------------------------
# The HTTP transport (DESIGN.md:901-906, :778-782).
# ----------------------------------------------------------------------


def test_http_without_tokens_is_a_startup_failure(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """DESIGN.md:905-906: an open server is the alternative.

    So it refuses.
    """
    clean_env.setenv("JOBVITE_MCP_TRANSPORT", "http")
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    _set(clean_env, V2_PAIR)
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()
    assert "JOBVITE_HTTP_TOKENS" in str(excinfo.value)


def test_http_with_tokens_starts(clean_env: pytest.MonkeyPatch) -> None:
    """The positive control for the case above."""
    clean_env.setenv("JOBVITE_MCP_TRANSPORT", "http")
    clean_env.setenv("JOBVITE_HTTP_TOKENS", json.dumps({"tok": ["jobs:read"]}))
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    _set(clean_env, V2_PAIR)
    assert load_settings().mcp_transport == "http"


def test_stdio_without_tokens_starts(clean_env: pytest.MonkeyPatch) -> None:
    """The token requirement is keyed on the TRANSPORT, not on a tool.

    DESIGN.md:1021-1026 sets that row of the matrix apart for this
    reason, so the negative belongs here: stdio must not inherit an HTTP
    obligation.
    """
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    _set(clean_env, V2_PAIR)
    assert load_settings().http_tokens is None


def test_a_malformed_token_map_is_refused_without_echoing_it(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """A malformed value refuses, and the refusal quotes no part of it.

    The value is secret-class (DESIGN.md:901-904) and a JSON parse
    error's own text quotes its input, so the exception must be
    discarded rather than reported.
    """
    secret = "s3cr3t-token-material"  # noqa: S105 - the point of the case
    clean_env.setenv("JOBVITE_MCP_TRANSPORT", "http")
    clean_env.setenv("JOBVITE_HTTP_TOKENS", secret)
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    _set(clean_env, V2_PAIR)
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()
    assert "JOBVITE_HTTP_TOKENS" in str(excinfo.value)
    assert secret not in str(excinfo.value)


@pytest.mark.parametrize(
    ("key", "why"),
    [
        ("", "the empty string is not a bearer token"),
        ("   ", "a whitespace-only key is not a bearer token"),
        ("\t\n", "nor is one made of other whitespace"),
    ],
)
def test_an_empty_bearer_token_key_is_refused(
    clean_env: pytest.MonkeyPatch, key: str, why: str
) -> None:
    """R3-M1: `_token_map_problems` read only `.values()`.

    The KEYS are the bearer tokens, and nothing looked at them, so
    `{"": ["jobs:read"]}` was a non-empty object holding no usable
    credential - the "open server" condition at `config.py:19-20` in a
    different shape. Proved to boot before the fix.
    """
    clean_env.setenv("JOBVITE_MCP_TRANSPORT", "http")
    clean_env.setenv("JOBVITE_HTTP_TOKENS", json.dumps({key: ["jobs:read"]}))
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    _set(clean_env, V2_PAIR)
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()
    assert "JOBVITE_HTTP_TOKENS" in str(excinfo.value), why


def test_a_token_mapped_to_no_scopes_is_refused(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """R3-L2: a token that authenticates and authorises nothing.

    Accepting it defers the failure from boot - where the refusals are
    specified to happen - to the first request that needs a scope.
    """
    clean_env.setenv("JOBVITE_MCP_TRANSPORT", "http")
    clean_env.setenv("JOBVITE_HTTP_TOKENS", json.dumps({"tok": []}))
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    _set(clean_env, V2_PAIR)
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()
    assert "JOBVITE_HTTP_TOKENS" in str(excinfo.value)


def test_a_token_mapped_to_a_blank_scope_is_refused(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """A scope of `"  "` grants nothing and names nothing.

    This test exists because AMPUTATION found the guard unprotected:
    deleting the whitespace-scope branch left all 52 tests green, so the
    branch was correct code that nothing exercised. The empty-key and
    empty-list arms each killed their amputation; this one did not,
    which is the only reason the gap was visible at all.
    """
    clean_env.setenv("JOBVITE_MCP_TRANSPORT", "http")
    clean_env.setenv("JOBVITE_HTTP_TOKENS", json.dumps({"tok": ["  "]}))
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    _set(clean_env, V2_PAIR)
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()
    assert "JOBVITE_HTTP_TOKENS" in str(excinfo.value)


def test_a_refusal_over_a_bad_key_never_echoes_the_token_map(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """The new refusals keep the existing no-echo discipline.

    A message naming the offending key would publish token material from
    the very map it is rejecting, and the other keys in that map are
    real tokens.
    """
    live = "s3cr3t-live-token"  # noqa: S105 - the point of the case
    clean_env.setenv("JOBVITE_MCP_TRANSPORT", "http")
    clean_env.setenv(
        "JOBVITE_HTTP_TOKENS",
        json.dumps({"": ["jobs:read"], live: ["jobs:read"]}),
    )
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    _set(clean_env, V2_PAIR)
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()
    assert live not in str(excinfo.value)


def test_a_well_formed_token_map_still_boots(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """The negative arm.

    Without it, every refusal above passes on an implementation that
    rejects every token map ever written.
    """
    clean_env.setenv("JOBVITE_MCP_TRANSPORT", "http")
    clean_env.setenv(
        "JOBVITE_HTTP_TOKENS", json.dumps({"tok": ["jobs:read", "jobs:write"]})
    )
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    _set(clean_env, V2_PAIR)
    assert load_settings().mcp_transport == "http"


# ----------------------------------------------------------------------
# The off-loopback TLS refusal (DESIGN.md:873-876). Three High rows rest
# on it. The end-to-end process arms are in test_boot.py; these are the
# unit arms.
# ----------------------------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "[::1]"])
def test_loopback_addresses_are_recognised(host: str) -> None:
    assert is_loopback(host) is True


@pytest.mark.parametrize(
    "host",
    [
        "0.0.0.0",  # noqa: S104 - the wildcard bind is the point of the case
        "10.0.0.5",
        "::",
        "example.internal",
        "127.0.0.1.evil.example",
        "",
    ],
)
def test_non_loopback_and_unrecognisable_hosts_are_not_loopback(host: str) -> None:
    """Unrecognisable is NOT loopback: the fail-closed direction."""
    assert is_loopback(host) is False


def test_off_loopback_without_the_assertion_refuses(
    clean_env: pytest.MonkeyPatch,
) -> None:
    clean_env.setenv("JOBVITE_MCP_TRANSPORT", "http")
    clean_env.setenv("JOBVITE_MCP_HOST", "0.0.0.0")  # noqa: S104
    clean_env.setenv("JOBVITE_HTTP_TOKENS", json.dumps({"tok": ["jobs:read"]}))
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    _set(clean_env, V2_PAIR)
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()
    assert "JOBVITE_TLS_TERMINATED_BY_PROXY" in str(excinfo.value)
    assert "0.0.0.0" in str(excinfo.value)  # noqa: S104


def test_off_loopback_with_the_assertion_starts(clean_env: pytest.MonkeyPatch) -> None:
    """Positive control 1 of 2 for the refusal."""
    clean_env.setenv("JOBVITE_MCP_TRANSPORT", "http")
    clean_env.setenv("JOBVITE_MCP_HOST", "0.0.0.0")  # noqa: S104
    clean_env.setenv("JOBVITE_TLS_TERMINATED_BY_PROXY", "true")
    clean_env.setenv("JOBVITE_HTTP_TOKENS", json.dumps({"tok": ["jobs:read"]}))
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    _set(clean_env, V2_PAIR)
    assert load_settings().mcp_host == "0.0.0.0"  # noqa: S104


def test_the_default_loopback_bind_passes_validation(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """Positive control for the IN-PROCESS validator pair.

    Its partner is the off-loopback refusal above. `test_boot.py`
    holds the real-process pair; the two used to share one name
    (R3-N1).
    """
    clean_env.setenv("JOBVITE_MCP_TRANSPORT", "http")
    clean_env.setenv("JOBVITE_HTTP_TOKENS", json.dumps({"tok": ["jobs:read"]}))
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    _set(clean_env, V2_PAIR)
    assert load_settings().mcp_host == "127.0.0.1"


def test_the_tls_refusal_is_not_applied_on_stdio(clean_env: pytest.MonkeyPatch) -> None:
    """`JOBVITE_MCP_HOST` is only read when the transport is http.

    Without this the refusal would fire on a stdio deployment that
    happens to carry a leftover host value, which is a refusal nobody
    asked for.
    """
    clean_env.setenv("JOBVITE_MCP_HOST", "0.0.0.0")  # noqa: S104
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    _set(clean_env, V2_PAIR)
    assert load_settings().mcp_transport == "stdio"


def test_every_reason_is_named_not_just_the_first(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """§8 #10 requires the process to exit NAMING THE REASON.

    Raising at the first refusal would report the missing tokens and
    never the off-loopback bind, so the reason it was actually refused
    would never be printed.
    """
    clean_env.setenv("JOBVITE_MCP_TRANSPORT", "http")
    clean_env.setenv("JOBVITE_MCP_HOST", "0.0.0.0")  # noqa: S104
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    _set(clean_env, V2_PAIR)
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()
    assert len(excinfo.value.reasons) == 2
    joined = str(excinfo.value)
    assert "JOBVITE_HTTP_TOKENS" in joined
    assert "JOBVITE_TLS_TERMINATED_BY_PROXY" in joined


# ----------------------------------------------------------------------
# Empty is unset (the template ships empties on purpose).
# ----------------------------------------------------------------------


def test_an_empty_value_is_treated_as_unset(clean_env: pytest.MonkeyPatch) -> None:
    """`.env.example` ships secret-class values EMPTY on purpose.

    An operator copies it and fills only what their tools need, so an
    empty `JOBVITE_API_KEY` must be *absent*, not a present credential
    that is the empty string - which would satisfy the required-variable
    check and fail at Jobvite as the confusing 401 DESIGN.md:986-990
    exists to prevent.
    """
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    clean_env.setenv("JOBVITE_API_KEY", "")
    clean_env.setenv("JOBVITE_API_SECRET", "s")
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()
    assert "JOBVITE_API_KEY" in str(excinfo.value)


@pytest.mark.parametrize("blank", [" ", "   ", "\t", "\n", " \t \n "])
def test_a_whitespace_only_value_is_also_treated_as_unset(
    clean_env: pytest.MonkeyPatch, blank: str
) -> None:
    """A whitespace-only value is absent, which only half a test held.

    `_empty_is_unset` promises "empty AND whitespace-only" and only the
    first half was exercised.

    **This was a surviving mutation.** Deleting `.strip()` from the
    validator left the whole suite green, because every existing case
    uses `""` - which is falsy with or without the strip. A credential
    of `" "` would then be a PRESENT value that satisfies the
    required-variable check and fails at Jobvite as the confusing 401
    the rule exists to prevent, which is the empty-string defect wearing
    a space.

    A whitespace-only value is not exotic: it is what a `.env` line with
    a trailing space after the `=` produces, and what a copy-paste out
    of a terminal or a spreadsheet produces routinely.
    """
    clean_env.setenv("JOBVITE_TOOLS", "search_jobs")
    clean_env.setenv("JOBVITE_API_KEY", blank)
    clean_env.setenv("JOBVITE_API_SECRET", "s")
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()
    assert "JOBVITE_API_KEY" in str(excinfo.value), (
        f"a whitespace-only credential ({blank!r}) was accepted as present"
    )


@pytest.mark.parametrize("blank", ["", " ", "\t"])
def test_a_directly_constructed_blank_secret_is_also_unset(blank: str) -> None:
    """R2-nit-2: `_empty_is_unset` only ever looked at `str`.

    Environment variables are always `str`, so this cannot arrive from
    the environment - which is why it is a nit. But `Settings(...)` is
    constructed directly all over this suite (`test_config.py`,
    `test_server.py`), and a `SecretStr("")` built that way reached
    `_check_required_variables` as a PRESENT, empty credential: the
    exact condition the whole empty-is-unset rule exists to refuse,
    admitted through the one door that did not check.

    Held here rather than in `validate_settings` because the rule is
    already stated in one place and this is the same rule, not a second
    one - `_empty_is_unset` promised "empty and whitespace-only" and
    delivered it for one type.
    """
    settings = Settings(
        tools="search_jobs",
        api_key=SecretStr(blank),
        api_secret=SecretStr("s"),
    )
    with pytest.raises(ConfigurationError) as excinfo:
        validate_settings(settings)
    assert "JOBVITE_API_KEY" in str(excinfo.value), (
        f"a blank SecretStr ({blank!r}) was accepted as a present credential"
    )


def test_the_whole_committed_template_loads(clean_env: pytest.MonkeyPatch) -> None:
    """Every line of `.env.example` parses, and it still refuses.

    Copying the template verbatim must not be an int-parse crash - which
    is what `JOBVITE_PAGINATION_START_BASE=` (empty) would otherwise be.
    It must be an ordinary missing-credential refusal.
    """
    for line in ENV_EXAMPLE.read_text().splitlines():
        if line.startswith("JOBVITE_"):
            name, _, value = line.partition("=")
            clean_env.setenv(name, value)
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings()
    assert "JOBVITE_API_KEY" in str(excinfo.value)


# ----------------------------------------------------------------------
# The variable set is closed. DESIGN.md:1639-1643 makes `.env.example`
# the single enumeration; these DIFF the sets rather than counting them,
# which is the check that would have caught a three-variable gap in
# draft 2.
# ----------------------------------------------------------------------


def _env_example_names() -> set[str]:
    return set(re.findall(r"^(JOBVITE_[A-Z0-9_]+)=", ENV_EXAMPLE.read_text(), re.M))


def _design_names() -> set[str]:
    design = (REPO_ROOT / "docs" / "DESIGN.md").read_text()
    return set(re.findall(r"JOBVITE_[A-Z0-9_]+", design))


def _settings_names() -> set[str]:
    return {f"JOBVITE_{field.upper()}" for field in Settings.model_fields}


def _server_json_names() -> set[str]:
    data = json.loads((REPO_ROOT / "server.json").read_text())
    return {
        var["name"]
        for package in data["packages"]
        for var in package["environmentVariables"]
    }


def test_env_example_and_design_declare_the_same_variables() -> None:
    """DESIGN.md:1637-1643's check, as a DIFF and never as a count."""
    assert _env_example_names() == _design_names()


def test_settings_declares_exactly_the_template_variables() -> None:
    """`config.py` enumerates the set and invents none."""
    assert _settings_names() == _env_example_names()


def test_server_json_declares_every_variable() -> None:
    """DESIGN.md:1028-1029: `server.json` declares EVERY variable."""
    assert _server_json_names() == _env_example_names()


def test_every_known_tool_declares_its_required_variables() -> None:
    """R3-L1: an unlisted tool would boot requiring no credential.

    `missing_for` used `TOOL_REQUIREMENTS.get(tool, ())`, so a tool in
    `KNOWN_TOOLS` and absent from `TOOL_REQUIREMENTS` reported nothing
    missing, drew no refusal, and started with no credential at all.

    The neighbouring `test_the_tool_names_are_the_five_of_the_design`
    LOOKS like it covers this and does not: it checks `KNOWN_TOOLS`
    against the design prose and its own cardinality, and says nothing
    about `TOOL_REQUIREMENTS`. The two sets were equal when this was
    written, so the defect was latent - and U5 adding `search_jobs` is
    exactly the change that would have made it live.
    """
    assert set(TOOL_REQUIREMENTS) == set(KNOWN_TOOLS), (
        "every tool must declare its required variables; a tool missing "
        "from TOOL_REQUIREMENTS boots with no credential requirement"
    )


def test_the_tool_names_are_the_five_of_the_design() -> None:
    """The allow-list is the design's tool surface, not a superset."""
    design = (REPO_ROOT / "docs" / "DESIGN.md").read_text()
    for tool in KNOWN_TOOLS:
        assert f"`{tool}`" in design
    assert len(KNOWN_TOOLS) == 5


def test_validate_settings_accepts_a_settings_object_directly() -> None:
    """`validate_settings` runs without touching the environment."""
    settings = Settings(
        tools="search_jobs",
        api_key=SecretStr("k"),
        api_secret=SecretStr("s"),  # noqa: S106
    )
    validate_settings(settings)
