import hashlib
import json
import posixpath
import unicodedata
from collections.abc import Mapping
from typing import Any, Literal, TypedDict, cast


class FindingValidationError(ValueError):
    """Raised when a finding payload is malformed or invalid."""


class FindingArtifactContent(TypedDict):
    """Canonical wire payload for a normalized SARIF finding artifact."""

    type: Literal["finding"]
    address: str
    identity: dict[str, Any]
    location: dict[str, Any]
    provenance: dict[str, str]
    sarif_result: dict[str, Any]


def _required_mapping(value: Mapping[str, Any], key: str, path: str) -> Mapping[str, Any]:
    child = value.get(key)
    if not isinstance(child, Mapping):
        raise FindingValidationError(f"finding SARIF result is missing required field {path}.{key}")
    return cast(Mapping[str, Any], child)


def _required_string(value: Mapping[str, Any], key: str, path: str) -> str:
    child = value.get(key)
    if not child or not isinstance(child, str):
        raise FindingValidationError(f"finding SARIF result is missing required field {path}.{key}")
    return child


def _canonical_text(value: str) -> str:
    """Fold the platform-dependent spellings of the same text into one form."""
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


def _normalise_artifact_uri(uri: str) -> str:
    normalised = posixpath.normpath(_canonical_text(uri).replace("\\", "/"))
    if normalised in {"", "."}:
        raise FindingValidationError("finding SARIF result has an empty normalized artifact URI")
    return normalised.removeprefix("./")


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_finding_address_preimage(
    sarif_result: Mapping[str, Any],
    *,
    tool: str,
    tool_version: str,
    pinned_ruleset_or_feed_digest: str,
    invocation_argv_hash: str,
    target: str,
) -> dict[str, Any]:
    """Return the exact preimage dictionary whose JSON form is hashed for the finding address."""
    rule_id = _required_string(sarif_result, "ruleId", "result")
    locations = sarif_result.get("locations")
    if not isinstance(locations, list) or not locations or not isinstance(locations[0], Mapping):
        raise FindingValidationError("finding SARIF result is missing required field result.locations[0]")
    physical = _required_mapping(cast(Mapping[str, Any], locations[0]), "physicalLocation", "result.locations[0]")
    artifact_location = _required_mapping(physical, "artifactLocation", "result.locations[0].physicalLocation")
    uri = _normalise_artifact_uri(
        _required_string(artifact_location, "uri", "result.locations[0].physicalLocation.artifactLocation")
    )
    region = _required_mapping(physical, "region", "result.locations[0].physicalLocation")
    snippet = _required_mapping(region, "snippet", "result.locations[0].physicalLocation.region")
    snippet_text = _required_string(snippet, "text", "result.locations[0].physicalLocation.region.snippet")

    start_line = region.get("startLine")
    end_line = region.get("endLine", start_line)
    if not isinstance(start_line, int) or start_line < 1:
        raise FindingValidationError(
            "finding SARIF result is missing required field result.locations[0].physicalLocation.region.startLine"
        )
    if not isinstance(end_line, int) or end_line < start_line:
        raise FindingValidationError(
            "finding SARIF result has invalid field result.locations[0].physicalLocation.region.endLine"
        )
    start_column = region.get("startColumn", 1)
    end_column = region.get("endColumn", start_column)
    if not isinstance(start_column, int) or start_column < 1:
        raise FindingValidationError(
            "finding SARIF result has invalid field result.locations[0].physicalLocation.region.startColumn"
        )
    if not isinstance(end_column, int) or end_column < start_column:
        raise FindingValidationError(
            "finding SARIF result has invalid field result.locations[0].physicalLocation.region.endColumn"
        )

    provenance = {
        "tool": tool,
        "tool_version": tool_version,
        "pinned_ruleset_or_feed_digest": pinned_ruleset_or_feed_digest,
        "invocation_argv_hash": invocation_argv_hash,
        "target": target,
    }
    for key, value in provenance.items():
        if not value:
            raise FindingValidationError(f"finding provenance requires non-empty {key}")

    identity: dict[str, Any] = {
        "rule_id": rule_id,
        "artifact_uri": uri,
        # Absolute lines are deliberately excluded: inserting blank lines above
        # an unchanged finding must not change its content address.
        "region": {
            "line_span": end_line - start_line,
            "start_column": start_column,
            "end_column": end_column,
        },
        "snippet_hash": sha256_bytes(_canonical_text(snippet_text).encode("utf-8")),
    }
    return {"identity": identity, "provenance": provenance}


def build_finding_content(
    sarif_result: Mapping[str, Any],
    *,
    tool: str,
    tool_version: str,
    pinned_ruleset_or_feed_digest: str,
    invocation_argv_hash: str,
    target: str,
) -> FindingArtifactContent:
    """Normalize one SARIF 2.1.0 result into a provenance-bound finding."""
    address_preimage = build_finding_address_preimage(
        sarif_result,
        tool=tool,
        tool_version=tool_version,
        pinned_ruleset_or_feed_digest=pinned_ruleset_or_feed_digest,
        invocation_argv_hash=invocation_argv_hash,
        target=target,
    )

    address = sha256_bytes(canonical_json_bytes(address_preimage))

    locations = sarif_result.get("locations", [])
    location_0 = cast(Mapping[str, Any], locations[0])
    physical = cast(Mapping[str, Any], location_0.get("physicalLocation", {}))
    region = cast(Mapping[str, Any], physical.get("region", {}))

    start_line = region.get("startLine", 1)
    end_line = region.get("endLine", start_line)
    start_column = region.get("startColumn", 1)
    end_column = region.get("endColumn", start_column)

    return cast(
        FindingArtifactContent,
        {
            "type": "finding",
            "address": address,
            "identity": address_preimage["identity"],
            "location": {
                "artifact_uri": address_preimage["identity"]["artifact_uri"],
                "start_line": start_line,
                "end_line": end_line,
                "start_column": start_column,
                "end_column": end_column,
            },
            "provenance": address_preimage["provenance"],
            "sarif_result": dict(sarif_result),
        },
    )
