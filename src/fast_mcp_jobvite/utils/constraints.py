"""Shared inbound constraint types for input models (ADR-0012).

**Every input model imports its constraints from here. No input model
defines its own** - DESIGN.md:300-301 and ADR-0012, which is
**Accepted** and applied into SS3's module block at the freeze.

**Why the rule exists.** ADR-0012 records that housing the input
models without housing their validators re-runs the ownership
ambiguity one layer down: three units write input models, and a
control-character rule copied into each of them is three rules that
must agree. The duplication is "the first thing an implementer would
factor out on sight", so the module is specified rather than left to
whoever noticed.

**What a violation looks like to a caller: nothing shaped like a
problem object.** DESIGN.md:608-628 is explicit that every check here
lives in the input models, therefore runs **before the tool body**,
and is raised by the framework - so by SS5.1's own reasoning (a
problem object is safe precisely because it is *returned* rather than
*raised*) none of these rejections can return one. That is SS5.1's
third exception, not an exception to it. The rule still **fails
closed**, which is the whole of what B25 and B30 require.

**Why the character rule is not covered by `max_length` or by the
output allow-list** (DESIGN.md:176-183). A name carrying a NUL or a
bidi override is a well-formed short string, so every length and
regex check passes it. The allow-list is an **output** filter and
SS6.1's fencing applies on the way back out, so neither reaches an
inbound argument on its way to Jobvite.

**Scope actually built here, stated rather than implied.** This module
holds the **character rule** of DESIGN.md:172-179 AND the three
structural limits of DESIGN.md:162-164 - nesting depth 5, 1,000 list
items, 100 dict keys - which U14 landed. **This paragraph used to say
they were "not here"**, on the reasoning that no input model was
deeper than one flat object so the code would have no caller. That
reasoning was about the MODELS and the limits are about the PAYLOAD:
a caller sends whatever it likes, and a flat model receiving a
1,001-item list is exactly the shape the limits bound. The deferral
also named its own trigger - "the first nested input model" - and
`create_candidate` landed FLAT, so the trigger could never fire while
the obligation stayed open. See `InboundModel` below.

**The 1 MiB body limit of DESIGN.md:165 is discharged ELSEWHERE, and
this module is still not where it lives.** `check_structural_limits`
bounds the serialised size of the ARGUMENT PAYLOAD, which is a real
bound and is not the body cap: a request whose body never becomes an
argument payload is measured by nothing in this module. The cap itself
is now `http_hardening.BodySizeLimitMiddleware`, an `ASGIMiddleware`
mounted by `http_run_kwargs` - ADR-0029 as corrected by its ruling of
2026-08-29, which established that the seat existed and the row was a
gap rather than an impossibility.

**The two are not duplicates and neither may be deleted as one.** The
body cap is HTTP-only by construction, because stdio has no request
body; `MAX_PAYLOAD_BYTES` below is the only inbound size bound on the
stdio path and remains necessary.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Final

from pydantic import BaseModel, Field, StringConstraints, model_validator

#: C0 and C1 control characters, **except** tab, newline and carriage
#: return, which DESIGN.md:178-179 names as the three permitted ones.
#: `\x7f` (DEL) sits between the two ranges and is included.
_CONTROL_CHARACTERS: Final = r"\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f"

#: Unicode bidirectional overrides and isolates. A bidi override in a
#: string argument re-orders how a reviewer or a model reads the rest
#: of the line while leaving the bytes intact, which is why
#: DESIGN.md:178-179 names it beside the control characters rather
#: than leaving it to `max_length`.
#:
#: LRE/RLE/PDF/LRO/RLO, then LRI/RLI/FSI/PDI.
_BIDI_OVERRIDES: Final = "‪-‮⁦-⁩"

#: **`FORBIDDEN_CHARACTERS` USED TO SIT HERE AND IS DELETED.** It was a
#: `re.compile` of the same character class, introduced as "the PYTHON
#: engine's copy" for a caller that never arrived. Its own docstring
#: called it *"the one rule every inbound string is tested against"* -
#: and that was FALSE for as long as it existed: nothing imported it,
#: no test exercised it, and `SafeText` is validated by pydantic
#: against `_NO_FORBIDDEN` below, which is the Rust spelling and the
#: only spelling that runs.
#:
#: Review R4 recorded the same fact in passing (*"Nothing calls it"*,
#: `REVIEW-R4.md:175`) while fixing its sibling, and left the constant
#: in place. CodeQL's `py/unused-global-variable` found it again and
#: this time it is amputated rather than annotated, because a
#: definition nothing reads is inoperative code whose comment makes a
#: load-bearing claim - the worst of both, and the shape
#: `docs/OBLIGATIONS.md` forbids.
#:
#: If a Python-engine copy is ever genuinely needed, build it from
#: `_CONTROL_CHARACTERS` and `_BIDI_OVERRIDES` at the call site, so the
#: two spellings cannot drift apart unobserved.

#: A pattern admitting only strings that contain no forbidden
#: character.
#:
#: **`\A`/`\z` rather than `^`/`$`, and the reason is NOT a trailing
#: newline** (R4-L3). An earlier version of this comment said `^...$`
#: would admit a string ending in a newline and called that the
#: log-forging shape C7-T1 records. The anchor choice is right and
#: that justification was wrong: **newline is in the PERMITTED set**,
#: so `\A...\z` admits `"ab\n"` anyway - measured, `trailing NL
#: ACCEPTED`. The real reasons are that `$` would make the anchor
#: meaningless against a multi-line value, and that `\z` is the only
#: spelling the Rust engine has (see below).
#:
#: The log-forging protection the old comment claimed is real only for
#: `JobviteIdentifier`, whose alphabet excludes `\n` - and it is
#: `JobviteIdentifier` that the "trailing newline" arm in
#: `tests/test_tools_jobs.py` actually exercises. If a trailing
#: newline should be refused in log-bound free text, that is a
#: separate constraint type and a separate decision, not a property of
#: this anchor.
#:
#: **`\z`, not `\Z`, and this was MEASURED rather than transcribed.**
#: pydantic-core compiles patterns with the Rust `regex` crate, which
#: has no `\Z` and refuses the pattern at class-construction time:
#: `SchemaError: regex parse error ... unrecognized escape sequence`.
#: Python's own `re` spells the same anchor `\Z`, so a pattern copied
#: from Python docs fails here and a pattern copied from here would be
#: wrong in a `re.compile`. That asymmetry is why this module now
#: defines the rule in the Rust spelling ONLY: the deleted
#: `FORBIDDEN_CHARACTERS` was the Python-engine twin, and two spellings
#: of one rule with no caller on one of them is a drift waiting to
#: happen rather than a convenience. The character CLASS below is spelt
#: identically by both engines, so nothing is lost by keeping one.
#: **A NEGATED CLASS, NOT A LOOKAHEAD.** R4-H2: this read
#: `\A(?:(?![...]).)*\z`, and the Rust engine has NO look-around at
#: all, so declaring a single `SafeText` field raised `SchemaError:
#: look-around ... is not supported` at CLASS-CONSTRUCTION time. The
#: rule was written down, did not compile, and had no caller, so
#: nothing ever tried it.
#:
#: The comment directly above measured `\z` vs `\Z` against this same
#: engine and then introduced a second incompatibility two lines later.
#: A negated class is what it already recommends: "a character class,
#: which both engines spell identically".
_NO_FORBIDDEN = f"\\A[^{_CONTROL_CHARACTERS}{_BIDI_OVERRIDES}]*\\z"

#: Default ceiling for a free-form string argument. DESIGN.md:152-154
#: requires an explicit `max_length` on **every** string; this is the
#: value a field takes when it has no tighter reason of its own.
MAX_TEXT_LENGTH: Final = 256

#: Ceiling for a Jobvite identifier. `eId` is an opaque 8-character
#: identifier (DESIGN.md:510-512), and the ceiling is deliberately
#: looser than 8 because the width is `[INFERRED]` in the research and
#: a tighter bound would refuse a valid id on our own guess.
MAX_IDENTIFIER_LENGTH: Final = 64

#: A string argument: length-bounded, and free of control characters
#: and bidi overrides. **`strip_whitespace` is deliberately NOT set** -
#: silently rewriting an argument before validating it means the value
#: Jobvite receives is not the value the caller sent, and the audit
#: event would record the rewritten one.
SafeText = Annotated[
    str,
    StringConstraints(
        max_length=MAX_TEXT_LENGTH,
        pattern=_NO_FORBIDDEN,
    ),
]

#: A Jobvite identifier: alphanumerics, hyphen and underscore only.
#: DESIGN.md:152-154 requires a regex on **every** identifier, and this
#: one admits no character the forbidden set covers, so it discharges
#: the character rule by construction rather than by composition.
JobviteIdentifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=MAX_IDENTIFIER_LENGTH,
        pattern=r"\A[A-Za-z0-9_-]+\z",
    ),
]

#: A bounded positive count, for any argument that names a quantity.
PositiveCount = Annotated[int, Field(ge=1)]


# ----------------------------------------------------------------------
# THE STRUCTURAL LIMITS OF DESIGN.md:162-165 (SS2.1)
# ----------------------------------------------------------------------
#
# THIS BLOCK USED TO SAY THE LIMITS WERE ABSENT BY DECISION. It is
# rewritten rather than appended to, because two contradictory claims
# about the same module is worse than either one alone.
#
# The deferral's reasoning was: "no input model in the tree is deeper
# than one flat object, so a depth-5 check, a 1000-item check and a
# 100-key check would each have NO CALLER and NO REACHABLE TEST", with
# the trigger named as "the first nested input model".
#
# **THE REASONING CONFUSED THE MODEL WITH THE PAYLOAD, and its trigger
# could not fire.** A limit on inbound structure bounds what a CALLER
# SENDS, not what a model declares. Every one of these limits is
# reachable against a flat model today: a caller can post
# `{"ids": [[[[[[1]]]]]]}` or a 1,001-element list or a 200-key object
# at any of the five input models in this server, and before U14 the
# only thing between that payload and pydantic's own recursion was
# `extra="forbid"` firing for a DIFFERENT reason. Fail-closed by
# accident is the shape this repository keeps finding.
#
# And `create_candidate` - the tool the deferral named as its trigger -
# landed with SIX FLAT SCALAR FIELDS. The trigger was written so that
# it could not fire while the obligation stayed open.
#
#     Max nesting depth   5 levels     <- MAX_NESTING_DEPTH
#     Max list items      1,000        <- MAX_LIST_ITEMS
#     Max dict keys       100          <- MAX_DICT_KEYS
#     Max request body    1 MiB   <- NOT HERE, SEE BELOW
#
# THE FOURTH IS NOT THIS MODULE'S, AND ADR-0029 SAYS SO.
# DESIGN.md:165 and ADR-0012 both place body size "at the middleware".
# `MAX_PAYLOAD_BYTES` bounds the serialised ARGUMENT PAYLOAD, which is
# the largest thing this module can see. A body that never becomes an
# argument payload - a malformed frame, a body rejected by the JSON
# parser, a body on a non-tool route - is measured by nothing here.
#
# THAT RESIDUE IS NOW BOUNDED, at the layer that can see the bytes:
# `http_hardening.BodySizeLimitMiddleware`, mounted by
# `http_run_kwargs`, refusing on `Content-Length` where one is declared
# and on a running sum over the streamed body where one is not. The
# ruling on ADR-0029 dated 2026-08-29 corrected the ADR's own claim
# that there was no middleware to live in: `FastMCP.run_http_async`
# takes `middleware: list[ASGIMiddleware]`, and an ASGI middleware sees
# the raw body that our MCP-protocol `Middleware` objects never do.
#
# **`MAX_PAYLOAD_BYTES` IS STILL NOT THAT CAP AND IS NOT REDUNDANT.**
# The body cap is HTTP-only by construction - stdio carries no request
# body - so on stdio this constant is the only inbound size bound there
# is. Deleting it as a duplicate would leave that transport unbounded,
# and this comment exists so that reading the file does not suggest it.

#: SS2.1's nesting ceiling. The argument object itself is depth 1, so a
#: flat object of scalars is depth 1 and five levels of nesting is the
#: deepest ACCEPTED payload.
#: This module's own claim to a coverage role from DESIGN.md:1443-1445,
#: read by `docs/reviews/check-coverage-floors.py`. The design names the
#: roles and not the paths, and the claim lives HERE rather than in a
#: role-to-module map in the checker, which would be a hand-kept list
#: beside its container. The checker asserts the two sets are EQUAL.
COVERAGE_ROLE: Final = "argument rejection"

MAX_NESTING_DEPTH: Final = 5

#: SS2.1's list ceiling. 1,000 items is ACCEPTED; 1,001 is not.
MAX_LIST_ITEMS: Final = 1_000

#: SS2.1's mapping ceiling. 100 keys is ACCEPTED; 101 is not.
MAX_DICT_KEYS: Final = 100

#: SS2.1's body ceiling, applied to the serialised argument payload.
#: See the caveat above and ADR-0029.
#:
#: **AND IT UNDER-MEASURES THE WIRE BY UP TO 6x (R8-M2, measured).**
#: This re-serialises with `json.dumps(..., ensure_ascii=False)`, which
#: is NOT the bytes that arrived. A client may `\u`-escape any
#: character it likes, including printable ASCII, and `dumps` will not
#: put the escaping back:
#:
#:     wire the client sent  '{"k": "\u0041\u0041..."}'   6009 bytes
#:     what this measures    '{"k": "AA..."}'              1009 bytes
#:     under-measurement                                      5.96x
#:
#: So a ~5.9 MiB wire payload passes a 1 MiB cap. U14 parked this as
#: "conservative"; it is conservative about the object and not about
#: the wire, and the wire is what a body cap is for.
#:
#: **Left as-is deliberately, and the exact bound now EXISTS.** An
#: exact bound belongs where the bytes actually are, which is the ASGI
#: middleware seat ADR-0029 names - this module never sees them.
#: `http_hardening.MAX_REQUEST_BODY_BYTES` is that bound and is
#: byte-exact: it compares the caller's own `Content-Length`, or a
#: running sum of the bytes ASGI delivered, and re-serialises nothing.
#: **So the 6x residue below is now bounded on the HTTP transport at
#: the right layer, and remains UNBOUNDED on stdio**, where there is no
#: request body for a middleware to measure and this constant is the
#: only limit there is. Recorded here so the next reader does not have
#: to re-derive it, and so nobody "tightens" this constant believing it
#: bounds the body or deletes it believing the middleware replaced it.
#:
#: The first measurement of this taken here was itself wrong: comparing
#: `dumps(ensure_ascii=True)` against `dumps(ensure_ascii=False)` gives
#: a 3x ceiling, because it measures two re-serialisations rather than
#: the wire against one. The wire is whatever the client sent.
MAX_PAYLOAD_BYTES: Final = 1024 * 1024


def _measure(payload: object, depth: int) -> None:
    """Walk `payload`, raising on the first structural limit exceeded.

    `depth` is the depth of `payload` itself, counting from 1.

    **The check is BEFORE the descent, not after**, so a violation is
    reported at the level that carries it rather than one level down.

    **It is NOT what protects against a recursion blow-up, and an
    earlier version of this docstring said it was (R8-N1).**
    `json.dumps` at the size check runs FIRST and recurses before this
    function is entered, so ordering here cannot be the guard. The real
    margin is that `json.loads` gives out FIRST, measured here:

        depth  9997  -> ValueError, "nests deeper than 5 levels"
        depth  9998  -> json.loads raises RecursionError itself

    So every payload this code can be reached with is one the depth
    ceiling refuses cleanly, and anything deeper never parses. A cycle
    raises `ValueError('Circular reference detected')` from `dumps`.
    Both fail closed and reach the caller as a `ValidationError`, per
    `DESIGN.md:181-190`.

    That margin is a property of the stdlib, not of this code, so it is
    written down: a future change to the size check's `default=` or
    `ensure_ascii` could remove a protection nobody had recorded.
    """
    if depth > MAX_NESTING_DEPTH:
        raise ValueError(
            f"argument payload nests deeper than {MAX_NESTING_DEPTH} levels"
        )
    if isinstance(payload, dict):
        if len(payload) > MAX_DICT_KEYS:
            raise ValueError(
                f"argument payload carries more than {MAX_DICT_KEYS} keys "
                f"in one object ({len(payload)})"
            )
        for value in payload.values():
            _measure(value, depth + 1)
        return
    # `str` and `bytes` are Sequences and are NOT lists. Testing for
    # them by exclusion from `Sequence` is the form that admits the
    # type nobody thought of; `list`/`tuple`/`set` is the form that
    # names what it means.
    #
    # **`set` and `frozenset` are unreachable from `json.loads`, which
    # produces only dict/list/str/int/float/bool/None (R8-N2).** They
    # are here as defence for a non-JSON producer calling this
    # directly, and are named so nobody deletes them believing they
    # were reachable - or writes a coverage arm for a branch no wire
    # payload can enter.
    if isinstance(payload, (list, tuple, set, frozenset)):
        if len(payload) > MAX_LIST_ITEMS:
            raise ValueError(
                f"argument payload carries a collection of more than "
                f"{MAX_LIST_ITEMS} items ({len(payload)})"
            )
        for item in payload:
            _measure(item, depth + 1)


def check_structural_limits(payload: object) -> None:
    """Enforce SS2.1's structural limits on one argument payload.

    Raises `ValueError` on the first limit exceeded. **It raises rather
    than returning a problem object, and that is the design's own
    choice**: DESIGN.md:181-190 records that every check in the input
    models runs before the tool body and is raised by the framework, so
    nothing on this path can return one. The rule fails closed, which
    is the whole of what B25 and B30 require.

    Args:
        payload: The raw inbound arguments, before validation.

    Raises:
        ValueError: The payload exceeds one of SS2.1's four limits.
    """
    # SIZE FIRST, because it is the one limit whose violation makes the
    # walk expensive rather than merely wrong.
    #
    # `default=str` because this runs on a RAW payload that has not been
    # validated yet: a value pydantic would have rejected must not turn
    # a fail-closed size check into a TypeError from `json.dumps`.
    encoded = json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"argument payload is larger than {MAX_PAYLOAD_BYTES} bytes "
            f"({len(encoded)})"
        )
    _measure(payload, 1)


class InboundModel(BaseModel):
    """The base every tool's input model inherits.

    **This class is the CALLER the structural limits did not have.**
    ADR-0012 settles that the limits live in this module and explicitly
    leaves "whether the constraint types are Pydantic `Annotated`
    aliases, validators, or a base model" to the unit that builds them.
    A base model is chosen because the limits are properties of the
    PAYLOAD rather than of any one field, so there is no field to hang
    an `Annotated` alias on.

    **It deliberately sets no `model_config`.** Each input model
    declares `extra="forbid", strict=True` for itself, and
    `tests/test_arguments_sweep.py` asserts every enumerated model
    does - inheriting the config here would make that assertion pass
    for a model that never stated it, which is a green over a property
    nobody chose.
    """

    @model_validator(mode="before")
    @classmethod
    def _enforce_structural_limits(
        cls,
        data: Any,  # noqa: ANN401 - the RAW payload, before validation
    ) -> Any:  # noqa: ANN401 - returned unchanged, for pydantic
        """Refuse a payload past SS2.1's limits, before a field runs."""
        check_structural_limits(data)
        return data
