"""Configuration, and the boot-time refusals it owes.

DESIGN.md:982-1028.

`pydantic-settings` owns required-config validation. `fastmcp.json`
cannot express a required environment variable - with one unset the
server starts normally and the tool receives the literal string
`${JOBVITE_API_KEY}`, surfacing later as a confusing Jobvite 401
(DESIGN.md:984-988). So every refusal in this module happens at boot,
naming the variable.

Four refusals live here, and each one has the same direction: **fail
closed, loudly, before serving anything.**

1. **Per-enabled-tool required variables** (DESIGN.md:1011-1017). Never
   the union: a deployment using only candidate search must not be
   forced to invent a `companyId` it has no use for.
2. **An unrecognised `JOBVITE_TOOLS` name is a startup failure**
   (DESIGN.md:1002-1007), not a silent skip. A typo that silently
   disables a tool is a green start-up having done less than the
   operator asked.
3. **`JOBVITE_HTTP_TOKENS` unset while the transport is `http` is a
   startup failure** (DESIGN.md:899-905), not a server that starts with
   no tokens. The alternative is an open server.
4. **Off-loopback without TLS refuses to start** (DESIGN.md:871-875). A
   non-loopback bind carries a bearer token and candidate PII in the
   clear; `allowed_hosts` and `allowed_origins` address a different
   threat and do nothing about plaintext.

**Every refusal is collected, not raised at the first one.** §8 #10
requires that the process exit *naming the reason*, and an off-loopback
deployment that is also missing its tokens would otherwise be told only
about the tokens - the reason it was actually refused would never be
printed.

**Credentials are `SecretStr` throughout** (DESIGN.md:335-336), resolved
with `.get_secret_value()` only when building a request.
`JOBVITE_COMPANY_ID` is one of them: DESIGN.md:332 classifies it as the
job feed's separate credential, not as a public identifier.
"""

from __future__ import annotations

import ipaddress
import json
from typing import Any, Final, Literal

from pydantic import Field, SecretStr, model_validator
from pydantic import ValidationError as PydanticValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

#: The five tools of DESIGN.md:133-139, and the only names
#: `JOBVITE_TOOLS` accepts. A name outside this set is refused at boot.
SEARCH_CANDIDATES: Final = "search_candidates"
GET_CANDIDATE: Final = "get_candidate"
SEARCH_JOBS: Final = "search_jobs"
GET_JOB_FEED: Final = "get_job_feed"
CREATE_CANDIDATE: Final = "create_candidate"

#: The four reads. Unset `JOBVITE_TOOLS` means exactly these and never
#: the write (DESIGN.md:992-994).
READ_TOOLS: Final[frozenset[str]] = frozenset(
    {SEARCH_CANDIDATES, GET_CANDIDATE, SEARCH_JOBS, GET_JOB_FEED}
)

#: The one write. It is the only destructive tool and the only one
#: gated by `JOBVITE_ENABLE_WRITES` (DESIGN.md:207-229).
WRITE_TOOLS: Final[frozenset[str]] = frozenset({CREATE_CANDIDATE})

KNOWN_TOOLS: Final[frozenset[str]] = READ_TOOLS | WRITE_TOOLS

#: DESIGN.md:1011-1017's matrix, transcribed row by row. The `http` row
#: is not here because it is keyed on the transport rather than on a
#: tool, which is the distinction DESIGN.md:1019-1024 sets that row
#: apart to make.
TOOL_REQUIREMENTS: Final[dict[str, tuple[str, ...]]] = {
    SEARCH_CANDIDATES: ("api_key", "api_secret"),
    GET_CANDIDATE: ("api_key", "api_secret"),
    SEARCH_JOBS: ("api_key", "api_secret"),
    GET_JOB_FEED: ("feed_key", "feed_secret", "company_id"),
    CREATE_CANDIDATE: ("api_key", "api_secret"),
}

#: Hostnames that are loopback but are not IP literals, so
#: `ipaddress.ip_address` cannot classify them.
_LOOPBACK_NAMES: Final[frozenset[str]] = frozenset({"localhost"})


class ConfigurationError(Exception):
    """A boot-time refusal.

    Never reaches a caller, so it is not a problem.

    `errors.py` builds RFC 9457 problem objects for conditions a
    *caller* sees. This one is raised before anything is served, so it
    has no `request_id` to correlate against and no wire to travel on.
    It carries the collected reasons instead, so `__main__` can name
    every one of them on the way out.
    """

    def __init__(self, reasons: list[str]) -> None:
        """Record every reason the configuration was refused.

        Args:
            reasons: One line per refusal, each naming the variable or
                the tool it is about.
        """
        super().__init__("; ".join(reasons))
        self.reasons = list(reasons)


def _is_blank(value: object) -> bool:
    """True for an empty or whitespace-only string, however it arrived.

    **`SecretStr` is checked too (R2-nit-2).** This used to be an inline
    `isinstance(value, str)`, so a `Settings(api_key=SecretStr(""))` -
    the shape this suite constructs directly all over `test_config.py`
    and `test_server.py` - travelled past the empty-is-unset rule and
    reached `_check_required_variables` as a PRESENT, empty credential.
    Environment variables are always `str`, so this cannot fire from the
    environment; it is the direct-construction door that was not
    checked.

    Args:
        value: Any value from the raw settings mapping.

    Returns:
        True if the value is a string, or a secret wrapping a string,
        that carries nothing but whitespace.
    """
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    return isinstance(value, str) and not value.strip()


def env_name(field: str) -> str:
    """Return the environment variable a settings field reads.

    Refusal messages must name the variable an operator sets, not the
    Python attribute. Keeping the mapping in one function means a
    message and the model cannot drift.

    Args:
        field: The `Settings` attribute name, e.g. `api_key`.

    Returns:
        The environment variable name, e.g. `JOBVITE_API_KEY`.
    """
    return f"JOBVITE_{field.upper()}"


def is_loopback(host: str) -> bool:
    """Return whether a bind address is loopback.

    **Anything unrecognised is treated as NOT loopback**, which is the
    fail-closed direction: an unresolvable or misspelled host refuses to
    start rather than binding somewhere the TLS check never examined.

    Args:
        host: The value of `JOBVITE_MCP_HOST`, possibly a bracketed IPv6
            literal such as `[::1]`.

    Returns:
        True only for a loopback IP literal or a known loopback name.
    """
    candidate = host.strip().strip("[]")
    if candidate.lower() in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


class Settings(BaseSettings):
    """The fifteen variables, and nothing else.

    The set is closed: `.env.example` and DESIGN.md hold the same
    fifteen, and DESIGN.md:1637-1641 makes `.env.example` the single
    enumeration everything else is checked against rather than a second
    hand-kept list.

    `extra="ignore"` rather than `forbid`: the process environment
    carries hundreds of unrelated variables, and `forbid` would refuse
    to start on `PATH`. The `JOBVITE_` prefix is what bounds the
    surface.
    """

    model_config = SettingsConfigDict(
        env_prefix="JOBVITE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Jobvite v2 credentials
    # -------------------------------------------
    api_key: SecretStr | None = None
    api_secret: SecretStr | None = None

    # --- Jobvite v1 job-feed credentials
    # ----------------------------------
    feed_key: SecretStr | None = None
    feed_secret: SecretStr | None = None
    company_id: SecretStr | None = None

    # --- Tool surface
    # ------------------------------------------------------
    tools: str | None = None
    enable_writes: bool = False

    # --- Transport
    # ---------------------------------------------------------
    mcp_transport: Literal["stdio", "http"] = "stdio"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = Field(default=8000, ge=1, le=65535)
    http_tokens: SecretStr | None = None
    tls_terminated_by_proxy: bool = False

    # --- Limits
    # ------------------------------------------------------------
    #: DESIGN.md:1663-1666. 50 is the figure the caller-facing string
    #: `showing 50 of 1,240` already uses, not an arbitrary pick.
    max_results: int = Field(default=50, ge=1)
    #: DESIGN.md:1667-1672. **A conservative guess, not a vendor
    #: figure** - Jobvite documents no numeric limit at all. Checklist
    #: row 9 is what replaces it with an observation.
    outbound_rate_limit: int = Field(default=6, ge=1)
    #: DESIGN.md:1673-1678 (ADR-0027). §4.3 requires the total outbound
    #: budget to be **configured**, and until ADR-0027 named it the
    #: design demanded a variable no other section admitted existed.
    #: The default mirrors `DEFAULT_OUTBOUND_BUDGET_SECONDS` and is a
    #: choice, not a measurement - nothing about Jobvite's latency has
    #: ever been observed on this project.
    outbound_budget_seconds: float = Field(default=60.0, gt=0)

    # --- Jobvite quirks
    # ----------------------------------------------------
    pagination_start_base: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _empty_is_unset(cls, data: Any) -> Any:  # noqa: ANN401
        """Treat an empty value as absent: the template ships empties.

        `.env.example` ships every secret-class value **empty on
        purpose** (DESIGN.md's C8-I1 position), and an operator copies
        that file to `.env` and fills in only the variables their tools
        need. Without this, `JOBVITE_PAGINATION_START_BASE=` is an int
        parse failure and `JOBVITE_API_KEY=` is a *present* credential
        that is the empty string - which would satisfy the
        required-variable check and then fail at Jobvite as a 401, the
        exact confusion DESIGN.md:984-988 exists to prevent.

        Args:
            data: The raw mapping pydantic-settings assembled, or
                whatever else a caller passed.

        Returns:
            The same data with empty and whitespace-only strings
            removed, so each such field falls back to its default.
        """
        if not isinstance(data, dict):
            return data
        return {key: value for key, value in data.items() if not _is_blank(value)}

    def split_tool_names(self) -> tuple[frozenset[str], list[str]]:
        """Split `JOBVITE_TOOLS` into recognised and unrecognised.

        Returns:
            The recognised names, and the unrecognised ones in the order
            they were written so a refusal can quote them back.
        """
        if self.tools is None:
            return frozenset(), []
        named = [part.strip() for part in self.tools.split(",")]
        named = [part for part in named if part]
        unknown = [part for part in named if part not in KNOWN_TOOLS]
        return frozenset(part for part in named if part in KNOWN_TOOLS), unknown

    @property
    def enabled_tools(self) -> frozenset[str]:
        """The tools that will be registered, after both gates.

        Unset `JOBVITE_TOOLS` means all **read** tools and never the
        write (DESIGN.md:992-994). The write additionally requires
        `JOBVITE_ENABLE_WRITES=true` **and** to be named, and
        DESIGN.md:996-1000 states the conjunction in both directions -
        so writes-on with `JOBVITE_TOOLS` unset registers **no write**,
        and naming the write without the flag registers no write
        either. In neither case is the result empty: the read tools are
        registered throughout, and only the write is withheld.
        (R2-nit-1: this said "registers nothing" twice, which is the
        wrong claim in the first case and reads as a stronger one than
        the code makes in the second.)

        Unrecognised names are excluded here and refused by
        `validate_settings`; this property never raises, so a caller
        that skipped validation gets a smaller tool set rather than a
        crash at registration time.

        Returns:
            The frozen set of tool names to register.
        """
        recognised, _ = self.split_tool_names()
        selected = READ_TOOLS if self.tools is None else recognised
        if not self.enable_writes:
            selected -= WRITE_TOOLS
        return frozenset(selected)

    def missing_for(self, tool: str) -> list[str]:
        """Return the required variables a tool is missing.

        Args:
            tool: A name from `KNOWN_TOOLS`.

        Returns:
            The environment variable names that are unset, in the order
            DESIGN.md:1011-1016's row lists them.
        """
        # R3-L1. This was `TOOL_REQUIREMENTS.get(tool, ())`, which
        # resolved an unlisted tool to the empty tuple: no missing
        # variables, so no refusal, so the tool booted requiring NO
        # credential at all. A rule that names its members sitting on a
        # branch that fails open on empty - the two shapes that have
        # produced the most findings here.
        #
        # Subscripting instead makes the omission a KeyError at boot,
        # which is the module's stated direction: "fail closed, loudly"
        # (config.py:9-10). A tool present in KNOWN_TOOLS and absent
        # from TOOL_REQUIREMENTS is a programming error, not a user's
        # input, so it should not be smoothed into a valid
        # configuration.
        return [
            env_name(field)
            for field in TOOL_REQUIREMENTS[tool]
            if getattr(self, field) is None
        ]


def validate_settings(settings: Settings) -> None:
    """Apply every boot-time refusal, collecting all reasons.

    Args:
        settings: The loaded settings.

    Raises:
        ConfigurationError: If any refusal fires. Its `reasons` carry
            one line per refusal, so §8 #10's requirement that the
            process exit *naming the reason* holds even when several
            fire at once.
    """
    reasons: list[str] = []
    _check_tool_names(settings, reasons)
    _check_required_variables(settings, reasons)
    _check_transport(settings, reasons)
    if reasons:
        raise ConfigurationError(reasons)


def _check_tool_names(settings: Settings, reasons: list[str]) -> None:
    """Refuse an unknown `JOBVITE_TOOLS` name (DESIGN.md:1002-1007)."""
    _, unknown = settings.split_tool_names()
    for name in unknown:
        known = ", ".join(sorted(KNOWN_TOOLS))
        reasons.append(
            f"JOBVITE_TOOLS names an unrecognised tool {name!r}; "
            f"recognised tools are: {known}"
        )


def _check_required_variables(settings: Settings, reasons: list[str]) -> None:
    """Refuse a variable an ENABLED tool needs (DESIGN.md:1010-1018).

    Scoped to the enabled set and never the union: a deployment running
    only `search_candidates` is not asked for `JOBVITE_COMPANY_ID`.
    """
    for tool in sorted(settings.enabled_tools):
        missing = settings.missing_for(tool)
        if missing:
            reasons.append(
                f"tool {tool!r} is enabled but requires unset "
                f"variable(s): {', '.join(missing)}"
            )


def _check_transport(settings: Settings, reasons: list[str]) -> None:
    """Refuse an unsafe HTTP transport (DESIGN.md:871-875, :806-812).

    Two refusals, both keyed on the transport rather than on a tool,
    which is why DESIGN.md:1019-1024 sets that row of the matrix apart.
    """
    if settings.mcp_transport != "http":
        return
    if settings.http_tokens is None:
        reasons.append(
            "JOBVITE_MCP_TRANSPORT=http requires JOBVITE_HTTP_TOKENS; "
            "starting without it would serve an open server"
        )
    else:
        reasons.extend(_token_map_problems(settings.http_tokens))
    if not is_loopback(settings.mcp_host) and not settings.tls_terminated_by_proxy:
        reasons.append(
            f"JOBVITE_MCP_HOST={settings.mcp_host!r} is not a loopback address "
            "and JOBVITE_TLS_TERMINATED_BY_PROXY is not true: an off-loopback "
            "bind carries a bearer token and candidate PII in the clear. This "
            "server terminates no TLS of its own; put a terminating proxy in "
            "front and declare it"
        )


def _token_map_problems(raw: SecretStr) -> list[str]:
    """Check `JOBVITE_HTTP_TOKENS` parses to a token-to-scopes object.

    A malformed value is a boot-time refusal for the same reason an
    unset one is: the server would otherwise start holding no usable
    tokens.

    **No token, key or fragment of the value appears in any message
    here.** The value is secret-class (DESIGN.md:901-904), and a parse
    error's own text quotes the input, so the exception is deliberately
    discarded.

    Args:
        raw: The declared value.

    Returns:
        Zero or one refusal line.
    """
    try:
        parsed = json.loads(raw.get_secret_value())
    except json.JSONDecodeError:
        return ["JOBVITE_HTTP_TOKENS is not valid JSON"]
    if not isinstance(parsed, dict) or not parsed:
        return [
            "JOBVITE_HTTP_TOKENS must be a non-empty JSON object mapping each "
            'bearer token to its scopes, e.g. {"<token>": ["jobs:read"]}'
        ]
    # R3-M1. This loop read only `.values()`, so the KEYS - which are
    # the bearer tokens - were never examined at all.
    # `{"": ["jobs:read"]}` satisfied every check above and booted: a
    # non-empty object holding no usable credential, which is the "open
    # server" condition at config.py:19-20 wearing a different shape.
    if any(not isinstance(token, str) or not token.strip() for token in parsed):
        return [
            "JOBVITE_HTTP_TOKENS maps an empty or whitespace-only bearer "
            "token; every key must be a usable token"
        ]

    # Still `.values()`: no message here may name a token, so the key is
    # deliberately not bound in this loop.
    for scopes in parsed.values():
        if not isinstance(scopes, list) or not all(
            isinstance(scope, str) for scope in scopes
        ):
            return [
                "JOBVITE_HTTP_TOKENS maps a token to something other than a "
                "list of scope strings"
            ]
        # R3-L2, the same family: a token mapped to NO scopes
        # authenticates and can then authorise nothing. That is not a
        # usable credential either, and accepting it defers the failure
        # from boot - where the refusals are specified to happen - to
        # the first request.
        if not scopes:
            return [
                "JOBVITE_HTTP_TOKENS maps a token to an empty scope list; a "
                "token that holds no scope can authorise nothing"
            ]
        if any(not scope.strip() for scope in scopes):
            return [
                "JOBVITE_HTTP_TOKENS maps a token to an empty or whitespace-only scope"
            ]
    return []


def load_settings() -> Settings:
    """Load the environment and apply every boot-time refusal.

    **`Settings()` is inside the `try` on purpose (R2-M-2).** Seven
    fields carry pydantic constraints - the port range, the transport
    `Literal`, `max_results`, and the rest - and a value that fails one
    of them is a misconfiguration in exactly the sense
    `__main__.py:62-65` reserves `EXIT_CONFIGURATION_REFUSED` for. Left
    uncaught it exited **1 with a traceback**, so a mistyped port was
    indistinguishable to a supervisor from a crash, while every
    hand-written refusal beside it exited 78. One door for every
    boot-time refusal.

    **The reasons are rebuilt from `loc` and `msg`, never from
    `str(exc)`.** pydantic's rendering echoes the offending value back
    as `input_value=`, and a refusal message is written to a log. No
    secret-class field carries a constraint today, so nothing leaks
    through it right now; building the message this way is what keeps
    that true when one does.

    Returns:
        Settings that have passed every refusal.

    Raises:
        ConfigurationError: If any refusal fires.
    """
    try:
        settings = Settings()
    except PydanticValidationError as exc:
        # `from None` for the same reason as `audit.py`'s (R2-M-1): the
        # chained pydantic exception carries `input_value` in its own
        # text, and a traceback printing it would undo the line above.
        raise ConfigurationError(_validation_reasons(exc)) from None
    validate_settings(settings)
    return settings


def _validation_reasons(exc: PydanticValidationError) -> list[str]:
    """Turn a pydantic failure into refusal lines naming the variables.

    Args:
        exc: The validation error `Settings()` raised.

    Returns:
        One line per invalid field, naming the environment variable and
        pydantic's own explanation - and never the value.
    """
    reasons: list[str] = []
    for error in exc.errors():
        location = error["loc"]
        # A model-level error has an empty `loc` and names no field.
        # Reporting it without a variable name is worse than the
        # alternative only if the alternative is dropping it, which
        # would refuse the boot while naming nothing.
        where = env_name(str(location[0])) if location else "the configuration"
        reasons.append(f"{where}: {error['msg']}")
    return reasons
