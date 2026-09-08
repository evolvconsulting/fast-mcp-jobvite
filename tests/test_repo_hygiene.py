"""DESIGN.md §8 case #3 - the credential patterns and the env template.

`.gitignore` covers the credential patterns, and `.env.example` carries
no real value.

Asserted against the COMMITTED files, because the row this covers
(C8-I1) is about what reaches the repository rather than what reaches a
log.

**What this test must NOT assert, and why the negative statement is the
important half.** Draft 2 of the plan said "every value in
`.env.example` is empty". That is false against the committed tree and
it is dangerous. Seven of the fifteen variables carry a value; eight are
empty, and only SIX of those eight are secret-class - `JOBVITE_TOOLS`
and `JOBVITE_PAGINATION_START_BASE` are empty non-secrets. The cheapest
way to make "every value is empty" pass is to empty
`JOBVITE_MAX_RESULTS=50` and `JOBVITE_OUTBOUND_RATE_LIMIT=6`, which
un-answers the design's Q1 and re-blocks U1, U6 and U7
(PLAN-REVIEW-R2.md:255-270).

So the assertion is keyed on SECRET-CLASS, not on emptiness, and the
deliberate non-secret defaults are pinned positively so that an agent
"fixing" the tree by emptying them turns this red instead of green.
"""

from __future__ import annotations

import re

from fast_mcp_jobvite.config import Settings

from .conftest import ENV_EXAMPLE, GITIGNORE, REPO_ROOT

# DESIGN.md:1646-1651 counts five credential variables; §7.2 adds
# JOBVITE_HTTP_TOKENS, the bearer-token map, as the sixth secret-class
# name. Six, enumerated here and cross-checked against the file below so
# the list cannot silently go stale.
SECRET_CLASS = [
    "JOBVITE_API_KEY",
    "JOBVITE_API_SECRET",
    "JOBVITE_FEED_KEY",
    "JOBVITE_FEED_SECRET",
    "JOBVITE_COMPANY_ID",
    "JOBVITE_HTTP_TOKENS",
]

# Deliberate values. Emptying either is a regression, not a cleanup.
NON_SECRET_DEFAULTS = {
    "JOBVITE_MAX_RESULTS": "50",
    "JOBVITE_OUTBOUND_RATE_LIMIT": "6",
    "JOBVITE_MCP_TRANSPORT": "stdio",
    "JOBVITE_MCP_HOST": "127.0.0.1",
    "JOBVITE_MCP_PORT": "8000",
    "JOBVITE_ENABLE_WRITES": "false",
    "JOBVITE_TLS_TERMINATED_BY_PROXY": "false",
}

CREDENTIAL_PATTERNS = [".env", ".env.*", "*.key", "*.pem", "secrets/"]


def _declared_variables() -> dict[str, str]:
    """Parse `.env.example` to name -> value, from the file.

    Never from memory.
    """
    out: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([A-Z0-9_]+)=(.*)$", stripped)
        assert match, f"unparseable line in .env.example: {line!r}"
        out[match.group(1)] = match.group(2).strip()
    return out


def test_the_parser_actually_found_variables() -> None:
    """Positive control on the instrument.

    Every assertion below iterates a dict this parser produced. A parser
    that matched nothing would make all of them pass vacuously.
    """
    variables = _declared_variables()
    expected = {f"JOBVITE_{name.upper()}" for name in Settings.model_fields}
    assert set(variables) == expected, (
        f"parsed {sorted(variables)} from .env.example, "
        f"Settings declares {sorted(expected)}"
    )
    # The equality above is the claim; this is the positive control
    # ON IT. Two empty sets are equal, so the equality alone would pass
    # against a parser that matched nothing AND a Settings that
    # declared nothing.
    assert len(variables) > 1, (
        f"the parser found {len(variables)} variables, so every assertion in "
        f"this file that iterates it is vacuous"
    )


def test_every_secret_class_variable_is_empty() -> None:
    variables = _declared_variables()
    missing = [name for name in SECRET_CLASS if name not in variables]
    assert not missing, f".env.example does not declare {missing}"
    # NAMES ONLY. The only condition under which this fires is "a real
    # value is sitting in a secret-class slot", and this repository is
    # PUBLIC - a failure message goes into a world-readable Actions log,
    # which is exactly what credential-scanning vendors index. The
    # variable NAME is the whole diagnosis; the value adds nothing and
    # is the thing being protected. Length is offered for triage
    # instead. CREDENTIAL-CHECKLIST.md:88 requires the redaction to
    # happen before the capture touches disk.
    carrying = sorted(
        f"{name} ({len(variables[name])} chars)"
        for name in SECRET_CLASS
        if variables[name] != ""
    )
    assert not carrying, (
        "secret-class variables in .env.example carry a value. Names and lengths "
        f"only - the value is deliberately not printed: {carrying}"
    )


def test_the_deliberate_non_secret_defaults_are_intact() -> None:
    """The guard against emptying the values that answer Q1."""
    variables = _declared_variables()
    wrong = {
        name: (variables.get(name), expected)
        for name, expected in NON_SECRET_DEFAULTS.items()
        if variables.get(name) != expected
    }
    assert not wrong, f"non-secret defaults changed (got, expected): {wrong}"


def test_no_value_in_env_example_looks_like_a_real_credential() -> None:
    """DESIGN.md:1353 - no REAL value.

    A placeholder that looks like a credential is the thing a reader
    copies by accident and a scanner mistakes for a finding.
    """
    variables = _declared_variables()
    suspicious = {
        name: value
        for name, value in variables.items()
        if name in SECRET_CLASS or len(value) >= 20
    }
    # Names and lengths only, for the same reason as above: this
    # assertion fires only when a real-looking value is present, and
    # printing it publishes it.
    offenders = sorted(
        f"{name} ({len(value)} chars)"
        for name, value in suspicious.items()
        if value != ""
    )
    assert not offenders, (
        "values that could be mistaken for credentials, names and lengths only - "
        f"the value is deliberately not printed: {offenders}"
    )


def test_gitignore_covers_every_credential_pattern() -> None:
    entries = {
        line.strip()
        for line in GITIGNORE.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    missing = [pattern for pattern in CREDENTIAL_PATTERNS if pattern not in entries]
    assert not missing, f".gitignore does not cover {missing}"


def test_gitignore_does_not_negate_the_credential_patterns() -> None:
    """`!.env.example` is the one legal negation in `.gitignore`.

    Any other un-ignores a credential.

    Ignoring `.env.*` and then re-including something under it would
    restore exactly the hole the pattern list exists to close, and a
    membership check over the entries above cannot see a `!` line.
    """
    negations = {
        line.strip()
        for line in GITIGNORE.read_text().splitlines()
        if line.strip().startswith("!")
    }
    assert negations == {"!.env.example"}, (
        f"unexpected gitignore negations: {negations}"
    )


# ======================================================================
# TWO DECLARATIONS OF ONE DEFAULT. R7-M1.
# ======================================================================


def _dual_declared_defaults() -> list[str]:
    """Every model field declaring a default TWICE, as `file:line`.

    A field written as `x: Annotated[T, Field(default=A)] = B` has two
    declarations of one value. **Pydantic takes the assignment and the
    `Field` copy is inert** - measured on the locked pydantic 2.13.5,
    not cited: a model with `Field(default=True)` and `= False` reads
    back `False`, with no warning and no error.

    **This walks the container - every annotated field of every class
    in the tree - rather than keeping a list of the known instances
    beside it.** That distinction is the finding. U10's M9 first caught
    this shape on `send_email`, the one field in this server that
    decides whether a live person is emailed, and the fix left a note
    saying *"these three fields"* beside the three it repaired. R7 then
    found three MORE in `tools/jobs.py`, a file that fix never opened,
    by walking the tree instead of reading the note.

    Returns:
        One `path:line` per offending field, empty when clean.
    """
    import ast

    offenders: list[str] = []
    for path in sorted(REPO_ROOT.rglob("*.py")):
        if any(part in (".git", ".venv") for part in path.parts):
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for stmt in node.body:
                if not isinstance(stmt, ast.AnnAssign) or stmt.value is None:
                    continue
                for sub in ast.walk(stmt.annotation):
                    if not isinstance(sub, ast.Call):
                        continue
                    called = getattr(sub.func, "id", None) or getattr(
                        sub.func, "attr", None
                    )
                    if called != "Field":
                        continue
                    if any(
                        kw.arg in ("default", "default_factory") for kw in sub.keywords
                    ):
                        rel = path.relative_to(REPO_ROOT)
                        offenders.append(f"{rel}:{stmt.lineno}")
    return offenders


def test_the_dual_default_walk_actually_reaches_the_models() -> None:
    """POSITIVE CONTROL. An AST walk that parses nothing finds nothing.

    A clean result from the case below means "no field declares its
    default twice" only if the walk really visited the models. A bad
    root, a rename or a swallowed parse would produce the same empty
    list - the wrong-zero that explains itself.
    """
    import ast

    seen = set()
    for path in REPO_ROOT.rglob("*.py"):
        if any(part in (".git", ".venv") for part in path.parts):
            continue
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if isinstance(node, ast.ClassDef):
                seen.add(node.name)

    for model in ("SearchJobsInput", "GetJobFeedInput", "CreateCandidateInput"):
        assert model in seen, f"the walk never reached {model}; a clean run is vacuous"


def test_no_field_declares_its_default_twice() -> None:
    """R7-M1, and it is the same defect at the width of one field.

    R7's mutation M1 set the inert `Field(default=...)` copy on
    `SearchJobsInput.ids` to a type-invalid string and the whole suite
    passed, exit 0. Reproduced before fixing: 665 passed. All three
    offenders were in `tools/jobs.py`; the fix is three deletions,
    leaving the assignment as the single declaration.

    The blast radius was low - all three defaults are `None`, so
    flipping the inert copy changed no behaviour today. The defect is
    that the MECHANISM was still live: the next field added in this
    shape may be one that matters, and `send_email` already proved
    which field that is.
    """
    offenders = _dual_declared_defaults()
    assert not offenders, (
        "these fields declare a default twice; pydantic takes the "
        f"assignment and the Field copy is inert: {offenders}"
    )
