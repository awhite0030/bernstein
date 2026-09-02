"""Artifact contract: kinds, canonical serialisation, and typed criteria (#2608).

Slice 1 of the generalised task/artifact contract. A non-coding agent produces
a *report*, a *dataset*, an *action log*, or an *ops result* instead of a code
diff. Each such artifact needs a single, byte-stable canonical form so its
``content_hash`` is a deterministic content-addressed identity: two operators
with equal inputs must produce byte-identical bytes, hence the same hash, hence
the same signed lineage entry.

Every canonicaliser routes through one shared core (stable key ordering, fixed
UTF-8, ``\\n`` newlines):

* text kinds (``code_diff`` / ``report``) normalise newlines to ``\\n`` and
  *reject* non-NFC input rather than repairing it - the same reject-don't-repair
  policy the other canonical cores in the codebase apply;
* JSONL kinds (``dataset`` / ``action_log``) emit one JCS-canonical JSON object
  per line, ``\\n``-separated;
* the JSON-object kind (``ops_result``) emits a single JCS-canonical object.

This module deliberately has no dependency on the task model or the lineage
store so it can be imported from both sides without a cycle.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, cast

from bernstein.core.finding_canonicaliser import (
    FindingValidationError,
    build_finding_address_preimage,
)
from bernstein.core.finding_canonicaliser import (
    canonical_json_bytes as _canonical_json_bytes,
)


class ArtifactKind(StrEnum):
    """Closed set of artifact kinds a task can declare it produces."""

    CODE_DIFF = "code_diff"
    REPORT = "report"
    DATASET = "dataset"
    ACTION_LOG = "action_log"
    OPS_RESULT = "ops_result"
    FINDING = "finding"
    BLOB = "blob"


#: Kinds whose canonical form is normalised UTF-8 *text*.
_TEXT_KINDS: frozenset[ArtifactKind] = frozenset({ArtifactKind.CODE_DIFF, ArtifactKind.REPORT})
#: Kinds whose canonical form is JSONL - one JCS object per line, ``\n``-joined.
_JSONL_KINDS: frozenset[ArtifactKind] = frozenset({ArtifactKind.DATASET, ArtifactKind.ACTION_LOG})
#: Kinds whose canonical form is a single JCS-canonical JSON object.
_JSON_OBJECT_KINDS: frozenset[ArtifactKind] = frozenset({ArtifactKind.OPS_RESULT})
#: Kinds whose canonical form is raw bytes.
_BYTE_KINDS: frozenset[ArtifactKind] = frozenset({ArtifactKind.BLOB})

#: The three typed criteria that operate on artifact bytes (issue #2608).
ARTIFACT_CRITERION_TYPES: frozenset[str] = frozenset({"schema_valid", "criteria_match", "hash_stable"})

#: Closed set of predicate operators the ``criteria_match`` evaluator accepts.
_ALLOWED_OPS: frozenset[str] = frozenset({"exists", "eq", "ne", "contains", "gt", "ge", "lt", "le"})


class CanonicalisationError(ValueError):
    """Raised when an artifact cannot be canonicalised under its kind's rule."""


class ArtifactSpecError(ValueError):
    """Raised when an operator-declared artifact block is malformed (#3110).

    ``field`` names the offending key as a dotted path rooted at the
    declaration key (e.g. ``artifact_spec.kind``), so every loader points the
    operator at the exact field that was wrong. Fail-closed on purpose: a
    malformed declaration stops the load. It must never default to
    ``code_diff``, because a task that silently completes on a git SHA is the
    wrong completion identity for the artifact the operator asked for.
    """

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


# ---------------------------------------------------------------------------
# Shared canonical core
# ---------------------------------------------------------------------------


def canonical_json_bytes(obj: Any) -> bytes:
    """Shared JSON canonical core: sorted keys, minimal separators, UTF-8.

    ``allow_nan=False`` rejects NaN / Infinity, which have no canonical JSON
    form. Every JSON-shaped kind routes through this single serialiser so two
    kinds can never disagree on key ordering or separators.
    """
    try:
        return json.dumps(
            obj,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CanonicalisationError(f"value is not canonical-JSON serialisable: {exc}") from exc


def _normalise_newlines(text: str) -> str:
    """Fold CRLF and a lone CR to ``\\n``. Part of the shared text core."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _canonical_text_bytes(text: str) -> bytes:
    """Shared text canonical core: normalise newlines, require NFC, encode UTF-8.

    Non-NFC text is *rejected*, not repaired, so a caller can never silently
    ship two byte-different inputs that render the same. Newline normalisation
    runs first; it only touches ASCII control bytes and so never changes NFC
    status.
    """
    normalised = _normalise_newlines(text)
    if not unicodedata.is_normalized("NFC", normalised):
        raise CanonicalisationError("text artifact is not NFC-normalised (reject-don't-repair policy)")
    return normalised.encode("utf-8")


def _coerce_text(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, bytes):
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CanonicalisationError(f"text artifact bytes are not valid UTF-8: {exc}") from exc
    raise CanonicalisationError(f"text artifact must be str or bytes, got {type(raw).__name__}")


def _coerce_rows(raw: Any) -> list[Any]:
    if isinstance(raw, (str, bytes, dict)):
        raise CanonicalisationError("JSONL artifact must be a sequence of JSON objects, not a scalar or mapping")
    try:
        return list(raw)
    except TypeError as exc:
        raise CanonicalisationError(f"JSONL artifact must be an iterable of rows: {exc}") from exc


# ---------------------------------------------------------------------------
# Per-kind canonicalisers + content hash
# ---------------------------------------------------------------------------


def _canonical_finding_bytes(raw: Any) -> bytes:
    """Canonicalise a SARIF 2.1.0 finding artifact for content-addressing.
    Delegates to the stricter, unified implementation from the evidence boundary.
    """
    if not isinstance(raw, dict):
        raise CanonicalisationError(f"finding artifact must be a mapping, got {type(raw).__name__}")

    raw_dict = cast(dict[str, Any], raw)
    sarif_result = raw_dict.get("sarif_result", raw_dict)
    provenance = raw_dict.get("provenance", raw_dict)

    if not isinstance(sarif_result, dict):
        raise CanonicalisationError("finding payload is missing required field sarif_result or it is not a dict")
    if not isinstance(provenance, dict):
        raise CanonicalisationError("finding payload is missing required field provenance or it is not a dict")

    typed_sarif_result = cast(dict[str, Any], sarif_result)
    typed_provenance = cast(dict[str, Any], provenance)

    try:
        content = build_finding_address_preimage(
            typed_sarif_result,
            tool=str(typed_provenance.get("tool", "")),
            tool_version=str(typed_provenance.get("tool_version", "")),
            pinned_ruleset_or_feed_digest=str(typed_provenance.get("pinned_ruleset_or_feed_digest", "")),
            invocation_argv_hash=str(typed_provenance.get("invocation_argv_hash", "")),
            target=str(typed_provenance.get("target", "")),
        )
    except FindingValidationError as exc:
        raise CanonicalisationError(str(exc)) from exc

    return _canonical_json_bytes(content)


def canonicalise_artifact(kind: ArtifactKind | str, raw: Any) -> bytes:
    """Return the canonical bytes for ``raw`` under ``kind``'s rule.

    Raises :class:`CanonicalisationError` when the input does not fit the
    kind's shape or violates the reject-don't-repair policy.
    """
    k = ArtifactKind(kind)
    if k in _TEXT_KINDS:
        return _canonical_text_bytes(_coerce_text(raw))
    if k in _JSONL_KINDS:
        rows = _coerce_rows(raw)
        return b"\n".join(canonical_json_bytes(row) for row in rows)
    if k in _JSON_OBJECT_KINDS:
        return canonical_json_bytes(raw)
    if k in _BYTE_KINDS:
        if isinstance(raw, bytes):
            return raw
        raise CanonicalisationError(f"blob artifact must be bytes, got {type(raw).__name__}")
    if k is ArtifactKind.FINDING:
        return _canonical_finding_bytes(raw)
    raise CanonicalisationError(f"no canonicaliser registered for kind {k!r}")


def content_hash(canonical_bytes: bytes) -> str:
    """Return the ``sha256:`` content hash of already-canonical bytes."""
    return "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()


def artifact_content_hash(kind: ArtifactKind | str, raw: Any) -> str:
    """Canonicalise ``raw`` under ``kind`` and return its content hash."""
    return content_hash(canonicalise_artifact(kind, raw))


def _parse_json_document(kind: ArtifactKind, canonical_bytes: bytes) -> Any:
    """Parse canonical artifact bytes back into a JSON document for criteria.

    JSONL kinds parse to a ``list`` of row objects; the JSON-object kind parses
    to the object. Text kinds have no JSON document and raise.
    """
    if kind in _JSONL_KINDS:
        if not canonical_bytes:
            return []
        return [json.loads(line) for line in canonical_bytes.split(b"\n")]
    if kind in _JSON_OBJECT_KINDS:
        return json.loads(canonical_bytes)
    raise CanonicalisationError(f"kind {kind.value!r} has no JSON document form")


# ---------------------------------------------------------------------------
# Typed criterion evaluators (closed set, never execute artifact-supplied code)
# ---------------------------------------------------------------------------


def evaluate_criterion(
    criterion_type: str,
    criterion_value: str,
    *,
    artifact: Any,
    kind: ArtifactKind | str,
) -> tuple[bool, str]:
    """Evaluate one typed artifact criterion against ``artifact``.

    Raises :class:`CanonicalisationError` when the artifact is malformed for
    the kind before the criterion logic runs.
    """
    if criterion_type == "hash_stable":
        # Any artifact kind can evaluate hash_stable, even blobs
        return _eval_hash_stable(kind, artifact, criterion_value)

    # schema_valid and criteria_match only work on parsed JSON documents
    if kind in _BYTE_KINDS:
        return False, f"criterion type {criterion_type!r} is not supported for blob kind"

    if criterion_type == "schema_valid":
        return _eval_schema_valid(kind, artifact, criterion_value)
    if criterion_type == "criteria_match":
        return _eval_criteria_match(kind, artifact, criterion_value)
    raise ValueError(f"unknown artifact criterion type {criterion_type!r}")


def _json_document_for(kind: ArtifactKind, artifact: Any) -> Any:
    """Return the JSON document (parsed from canonical bytes) for an artifact."""
    canonical = canonicalise_artifact(kind, artifact)
    return _parse_json_document(kind, canonical)


def _eval_schema_valid(kind: ArtifactKind, artifact: Any, schema_text: str) -> tuple[bool, str]:
    import jsonschema

    # Blob kind cannot be validated against JSON schema
    if kind in _BYTE_KINDS:
        return False, "criterion type 'schema_valid' is not supported for blob kind"

    try:
        schema = json.loads(schema_text)
    except json.JSONDecodeError as exc:
        return False, f"schema is not valid JSON: {exc}"
    try:
        doc = _json_document_for(kind, artifact)
    except CanonicalisationError as exc:
        return False, f"artifact has no JSON document to validate: {exc}"
    try:
        validator = jsonschema.Draft202012Validator(schema)
    except jsonschema.exceptions.SchemaError as exc:
        return False, f"schema is not a valid JSON Schema: {exc.message}"
    if kind in _JSONL_KINDS:
        for i, row in enumerate(doc):
            errors = sorted(validator.iter_errors(row), key=lambda e: list(e.path))
            if errors:
                return False, f"row {i} fails schema: {errors[0].message}"
        return True, f"all {len(doc)} row(s) valid"
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    if errors:
        return False, f"fails schema: {errors[0].message}"
    return True, "valid"


def _eval_hash_stable(kind: ArtifactKind, artifact: Any, expected_hash: str) -> tuple[bool, str]:
    if not expected_hash.startswith("sha256:"):
        return False, "criterion value must be a sha256: content hash"
    actual = artifact_content_hash(kind, artifact)
    if actual != expected_hash:
        return False, f"got {actual}, expected {expected_hash}"
    return True, "matches"


def _eval_criteria_match(kind: ArtifactKind, artifact: Any, expr_text: str) -> tuple[bool, str]:
    import boolean

    algebra = boolean.BooleanAlgebra()
    try:
        expr = algebra.parse(expr_text)
    except boolean.ParseError as exc:
        return False, f"criterion value is not a valid boolean expression: {exc}"

    try:
        doc = _json_document_for(kind, artifact)
    except CanonicalisationError as exc:
        return False, f"artifact has no JSON document to evaluate: {exc}"

    docs = doc if kind in _JSONL_KINDS else [doc]

    # Evaluate the expression against every row/document. They all must match.
    for i, cur in enumerate(docs):
        # A flat dictionary of leaf terms ("foo.bar eq baz" -> True/False)
        # populated strictly on demand.
        results: dict[boolean.Symbol, boolean.Symbol] = {}

        def _resolve_leaf(sym: boolean.Symbol) -> boolean.Symbol:
            if sym in results:
                return results[sym]
            ok, reason = _eval_leaf_predicate(sym.obj, cur)
            resolved = algebra.TRUE if ok else algebra.FALSE
            results[sym] = resolved
            return resolved

        final = expr.subs(_resolve_leaf)
        if final != algebra.TRUE:
            # Re-evaluate the failing row to find the first false leaf to
            # report, because `subs` evaluation order is internal to the AST.
            for sym in expr.symbols:
                ok, reason = _eval_leaf_predicate(sym.obj, cur)
                if not ok:
                    prefix = f"row {i} " if kind in _JSONL_KINDS else ""
                    return False, f"{prefix}fails predicate {sym.obj!r}: {reason}"
            return False, f"row {i} fails expression"

    return True, "matches"


def _eval_leaf_predicate(expr: Any, doc: Any) -> tuple[bool, str]:
    if not isinstance(expr, str):
        return False, "predicate must be a string"
    parts = expr.split(" ", 2)
    if len(parts) == 1:
        path, op, expected = parts[0], "exists", ""
    elif len(parts) == 3:
        path, op, expected = parts
    else:
        return False, f"malformed predicate: {expr!r}"

    if op not in _ALLOWED_OPS:
        return False, f"unknown operator {op!r} (allowed: {', '.join(sorted(_ALLOWED_OPS))})"

    try:
        actual = _resolve_json_path(doc, path)
    except KeyError:
        return False, f"path {path!r} not found"

    if op == "exists":
        return True, "exists"

    # Coerce both sides to float if possible for numeric operators
    def coerce(val: str | int | float) -> float | str:
        try:
            return float(val)
        except (ValueError, TypeError):
            return str(val)

    if op in {"gt", "ge", "lt", "le"}:
        left = coerce(actual)
        right = coerce(expected)
        try:
            if op == "gt":
                return left > right, "matches"  # type: ignore
            if op == "ge":
                return left >= right, "matches"  # type: ignore
            if op == "lt":
                return left < right, "matches"  # type: ignore
            if op == "le":
                return left <= right, "matches"  # type: ignore
        except TypeError:
            return False, f"cannot compare {type(left).__name__} and {type(right).__name__}"

    str_actual = str(actual)
    if op == "eq":
        if str_actual != expected:
            return False, f"got {str_actual!r}, expected {expected!r}"
        return True, "matches"
    if op == "ne":
        if str_actual == expected:
            return False, f"got {str_actual!r}, which equals {expected!r}"
        return True, "matches"
    if op == "contains":
        if expected not in str_actual:
            return False, f"got {str_actual!r}, which does not contain {expected!r}"
        return True, "matches"

    return False, f"unimplemented operator {op!r}"


def _resolve_json_path(doc: Any, path: str) -> Any:
    """Traverse a dotted path in a JSON document, arrays indexed by integer."""
    cur = doc
    for part in path.split("."):
        if isinstance(cur, list):
            try:
                idx = int(part)
                cur = cur[idx]
            except (ValueError, IndexError) as exc:
                raise KeyError(part) from exc
        elif isinstance(cur, dict):
            if part not in cur:
                raise KeyError(part)
            cur = cur[part]
        else:
            raise KeyError(part)
    return cur


# ---------------------------------------------------------------------------
# Declarative Artifact Contract (parseable from YAML / server payload)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ArtifactCriterion:
    """A typed criterion the agent's deliverable must pass to be accepted."""

    type: Literal["schema_valid", "criteria_match", "hash_stable"]
    value: str

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "value": self.value}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactCriterion:
        return cls(type=str(data.get("type")), value=str(data.get("value")))  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ArtifactSpec:
    """The contract governing the output of an artifact-producing task (#2608).

    Where a coding task completes on a git SHA, an artifact task completes on a
    content hash (see :class:`bernstein.core.lineage.spine.LineageSpine`). This
    spec defines what kind of artifact the agent must write and what validation
    rules it must pass before the completion path will accept it.

    This spec is the only source of truth for the task's deliverable format. It
    is parsed strictly from the operator's declaration (CLI flags or backlog
    frontmatter) via :func:`parse_artifact_spec` and frozen into the task plan.

    :attr:`kind` defines the expected shape (e.g. ``dataset``, ``report``).
    :attr:`canonicalisation` overrides the default byte-normalisation rule.
    :attr:`criteria` is a list of deterministic tests (e.g. JSON schema) that
    the canonicalised artifact bytes must pass.

    :attr:`output_path` is the workdir-relative location the agent must write
    the artifact to. It is what makes an artifact-mode task *executable*:
    the completion path reads those bytes, canonicalises them under
    :attr:`kind`, and records the signed lineage entry that stands in for the
    git SHA a coding task would have produced. An empty string selects the
    per-task default (see
    :func:`bernstein.core.tasks.artifact_completion.artifact_output_path`).
    """

    kind: ArtifactKind = ArtifactKind.CODE_DIFF
    canonicalisation: str = ""
    criteria: tuple[ArtifactCriterion, ...] = field(default_factory=tuple)
    output_path: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ArtifactKind):
            object.__setattr__(self, "kind", ArtifactKind(self.kind))
        if not isinstance(self.criteria, tuple):
            object.__setattr__(self, "criteria", tuple(self.criteria))

    @property
    def canonical_rule(self) -> str:
        """The effective canonicalisation rule id (falls back to the kind)."""
        return self.canonicalisation or self.kind.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "canonicalisation": self.canonicalisation,
            "criteria": [c.to_dict() for c in self.criteria],
            "output_path": self.output_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactSpec:
        criteria = tuple(ArtifactCriterion.from_dict(c) for c in data.get("criteria", []) if isinstance(c, dict))
        return cls(
            kind=ArtifactKind(str(data.get("kind", ArtifactKind.CODE_DIFF.value))),
            canonicalisation=str(data.get("canonicalisation", "")),
            criteria=criteria,
            output_path=str(data.get("output_path", "")),
        )

    @classmethod
    def default(cls) -> ArtifactSpec:
        """Return the default ``code_diff`` spec (the coding-task contract)."""
        return cls()


# ---------------------------------------------------------------------------
# The strict declaration parser shared by every operator surface (#3110)
# ---------------------------------------------------------------------------

#: YAML / payload key an operator declares the artifact contract under, and
#: the root of every :class:`ArtifactSpecError` field path.
ARTIFACT_SPEC_KEY = "artifact_spec"

_ALLOWED_SPEC_KEYS: frozenset[str] = frozenset({"kind", "canonicalisation", "criteria", "output_path"})
_ALLOWED_CRITERION_KEYS: frozenset[str] = frozenset({"type", "value"})


def validate_artifact_output_path(declared: str, *, field: str = f"{ARTIFACT_SPEC_KEY}.output_path") -> str:
    """Validate a declared artifact output path and return its POSIX form.

    The path must stay workdir-relative: absolute paths, drive-letter paths,
    and any ``..`` traversal are refused *at declaration time*, before a task
    exists and before any bytes are read. The same rules gate the completion
    path (:func:`bernstein.core.tasks.artifact_completion.artifact_output_path`),
    so a declaration that loads is one the completion path will accept.

    Raises:
        ArtifactSpecError: The path is absolute or escapes the workdir.
    """
    normalised = declared.replace("\\", "/")
    if normalised.startswith("/") or (len(normalised) > 2 and normalised[1:3] == ":/"):
        raise ArtifactSpecError(field, f"must be workdir-relative, got {declared!r}")
    if any(seg == ".." for seg in normalised.split("/")):
        raise ArtifactSpecError(field, f"must not traverse out of the workdir: {declared!r}")
    return normalised


def _parse_declared_criteria(raw: Any, *, root: str) -> tuple[ArtifactCriterion, ...]:
    """Parse the ``criteria`` list of a declaration. Strict; see the parser."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ArtifactSpecError(
            f"{root}.criteria", f"must be a list of {{type, value}} mappings, got {type(raw).__name__}"
        )
    parsed: list[ArtifactCriterion] = []
    for i, entry in enumerate(raw):
        path = f"{root}.criteria[{i}]"
        if not isinstance(entry, dict):
            raise ArtifactSpecError(path, f"must be a mapping with 'type' and 'value', got {type(entry).__name__}")
        unknown = sorted(set(map(str, entry)) - _ALLOWED_CRITERION_KEYS)
        if unknown:
            raise ArtifactSpecError(f"{path}.{unknown[0]}", "unknown key (allowed keys: type, value)")
        ctype = entry.get("type")
        if not isinstance(ctype, str) or ctype not in ARTIFACT_CRITERION_TYPES:
            allowed = ", ".join(sorted(ARTIFACT_CRITERION_TYPES))
            raise ArtifactSpecError(f"{path}.type", f"must be one of: {allowed}; got {ctype!r}")
        value = entry.get("value")
        if not isinstance(value, str) or not value.strip():
            raise ArtifactSpecError(f"{path}.value", "must be a non-empty string")
        parsed.append(ArtifactCriterion(type=ctype, value=value))  # type: ignore[arg-type]
    return tuple(parsed)


def parse_artifact_spec(raw: object) -> ArtifactSpec:
    """Parse an operator-declared ``artifact_spec`` block into an :class:`ArtifactSpec`.

    The one strict parser behind every declaration surface - the plan schema
    and loader, the backlog frontmatter, the CLI flags, and the task server's
    create boundary - so the surfaces cannot drift (issue #3110).

    Fail-closed by design. Anything malformed raises
    :class:`ArtifactSpecError` naming the offending field: an unknown kind, a
    missing or unsafe ``output_path``, an unknown key, a malformed criterion.
    Unknown keys are refused rather than ignored, because a typo'd key that is
    dropped silently turns a declared artifact contract into a default coding
    task - the exact defect this parser exists to close.

    Rules:

    * ``kind`` is required and must be a member of :class:`ArtifactKind`.
    * an artifact kind (anything but ``code_diff``) requires a non-empty,
      workdir-relative ``output_path`` - the declaration says *where* the
      deliverable lands, explicitly;
    * ``kind: code_diff`` is accepted bare (it restates the default coding
      contract) but takes no ``output_path`` and no ``criteria``;
    * ``canonicalisation`` may only name the kind's own default rule (or be
      omitted / empty) - no alternative rule ships, and accepting an unknown
      rule name would be a claim the completion path cannot honour;
    * each criterion is exactly ``{type, value}`` with a type from
      :data:`ARTIFACT_CRITERION_TYPES` and a non-empty string value.
    """
    root = ARTIFACT_SPEC_KEY
    if not isinstance(raw, dict):
        raise ArtifactSpecError(root, f"must be a mapping with a 'kind' field, got {type(raw).__name__}")
    unknown = sorted(set(map(str, raw)) - _ALLOWED_SPEC_KEYS)
    if unknown:
        allowed = ", ".join(sorted(_ALLOWED_SPEC_KEYS))
        raise ArtifactSpecError(f"{root}.{unknown[0]}", f"unknown key (allowed keys: {allowed})")

    kind_values = ", ".join(k.value for k in ArtifactKind)
    if "kind" not in raw:
        raise ArtifactSpecError(f"{root}.kind", f"is required (one of: {kind_values})")
    kind_raw = raw["kind"]
    if not isinstance(kind_raw, str):
        raise ArtifactSpecError(f"{root}.kind", f"must be a string, got {type(kind_raw).__name__}")
    try:
        kind = ArtifactKind(kind_raw)
    except ValueError:
        raise ArtifactSpecError(f"{root}.kind", f"unknown artifact kind {kind_raw!r} (one of: {kind_values})") from None

    output_raw = raw.get("output_path") or ""
    if not isinstance(output_raw, str):
        raise ArtifactSpecError(f"{root}.output_path", f"must be a string, got {type(output_raw).__name__}")
    output_path = output_raw.strip()

    if kind is ArtifactKind.CODE_DIFF:
        if output_path:
            raise ArtifactSpecError(
                f"{root}.output_path", "code_diff tasks complete on the git path and take no output_path"
            )
        if raw.get("criteria"):
            raise ArtifactSpecError(
                f"{root}.criteria", "code_diff tasks complete on the git path and take no artifact criteria"
            )
    else:
        if not output_path:
            raise ArtifactSpecError(
                f"{root}.output_path",
                f"is required for kind {kind.value!r}: the workdir-relative path the agent writes the artifact to",
            )
        output_path = validate_artifact_output_path(output_path)

    canon_raw = raw.get("canonicalisation") or ""
    if not isinstance(canon_raw, str):
        raise ArtifactSpecError(f"{root}.canonicalisation", f"must be a string, got {type(canon_raw).__name__}")
    canonicalisation = canon_raw.strip()
    if canonicalisation and canonicalisation != kind.value:
        raise ArtifactSpecError(
            f"{root}.canonicalisation",
            f"unknown rule {canonicalisation!r}; the only rule shipped for kind {kind.value!r} is its default"
            " (omit the key or repeat the kind)",
        )

    criteria = _parse_declared_criteria(raw.get("criteria"), root=root)
    # Blob kind only accepts hash_stable criterion; reject text-specific criteria at parse time
    if kind is ArtifactKind.BLOB:
        for criterion in criteria:
            if criterion.type in ("schema_valid", "criteria_match"):
                raise ArtifactSpecError(
                    f"{root}.criteria",
                    f"criterion type '{criterion.type}' is not supported for blob kind",
                )
    return ArtifactSpec(kind=kind, canonicalisation=canonicalisation, criteria=criteria, output_path=output_path)


__all__ = [
    "ARTIFACT_CRITERION_TYPES",
    "ARTIFACT_SPEC_KEY",
    "ArtifactCriterion",
    "ArtifactKind",
    "ArtifactSpec",
    "ArtifactSpecError",
    "CanonicalisationError",
    "artifact_content_hash",
    "canonicalise_artifact",
    "content_hash",
    "evaluate_criterion",
    "parse_artifact_spec",
    "validate_artifact_output_path",
]
