"""Donor profile for the volunteer-workers program (``.bernstein/volunteer_profile.json``)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

SUPPORTED_SCHEMA_VERSIONS = frozenset({1})


class VolunteerProfileError(ValueError):
    """A profile could not be loaded."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(f"{field}: {message}")


@dataclass(frozen=True, slots=True)
class DonorProfile:
    """A donor's declared volunteer policy.

    Attributes:
        version: Schema version; one of :data:`SUPPORTED_SCHEMA_VERSIONS`.
        allowed_projects: Allowlist of project repository URLs.
        allowed_licenses: Allowlist of OSI-approved SPDX identifiers.
        task_types: Allowlist of task types (e.g. "pytest", "mypy").
        size_caps: Max lines of code modified, max file size, etc.
        adapters_models: Which AI models/adapters can be used.
        cpu_ceiling: Max CPU cores allowed.
        ram_ceiling: Max RAM in GB allowed.
        gpu_ceiling: Max GPUs allowed.
        max_wall_clock_minutes: Max wall-clock time allowed per task.
        token_budget: Token budget for AI usage.
        egress_policy: Hostnames the sandbox may reach. Empty means no network.
        extensions: Fields this loader did not recognise, preserved verbatim.
    """

    version: int
    allowed_projects: tuple[str, ...]
    allowed_licenses: tuple[str, ...]
    task_types: tuple[str, ...]
    size_caps: Mapping[str, int]
    adapters_models: tuple[str, ...]
    cpu_ceiling: int | None
    ram_ceiling: int | None
    gpu_ceiling: int | None
    max_wall_clock_minutes: int | None
    token_budget: int | None
    egress_policy: tuple[str, ...]
    extensions: Mapping[str, Any]


def load_profile(source: str | bytes) -> DonorProfile:
    """Parse and validate a donor profile document."""
    text = source.decode("utf-8") if isinstance(source, bytes) else source
    try:
        raw = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VolunteerProfileError("<document>", f"not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise VolunteerProfileError("<document>", f"expected a JSON object, got {type(raw).__name__}")

    raw_dict = cast("dict[str, Any]", raw)
    version = _load_version(raw_dict)
    return DonorProfile(
        version=version,
        allowed_projects=_load_string_tuple(raw_dict, "allowed_projects"),
        allowed_licenses=_load_string_tuple(raw_dict, "allowed_licenses"),
        task_types=_load_string_tuple(raw_dict, "task_types"),
        size_caps=_load_int_mapping(raw_dict, "size_caps"),
        adapters_models=_load_string_tuple(raw_dict, "adapters_models"),
        cpu_ceiling=_load_optional_int(raw_dict, "cpu_ceiling"),
        ram_ceiling=_load_optional_int(raw_dict, "ram_ceiling"),
        gpu_ceiling=_load_optional_int(raw_dict, "gpu_ceiling"),
        max_wall_clock_minutes=_load_optional_int(raw_dict, "max_wall_clock_minutes"),
        token_budget=_load_optional_int(raw_dict, "token_budget"),
        egress_policy=_load_string_tuple(raw_dict, "egress_policy"),
        extensions=_load_extensions(raw_dict),
    )


def _load_version(raw: dict[str, Any]) -> int:
    if "version" not in raw:
        raise VolunteerProfileError("version", "required")
    value = raw["version"]
    if not isinstance(value, int) or isinstance(value, bool):
        raise VolunteerProfileError("version", f"expected an integer, got {type(value).__name__}")
    if value not in SUPPORTED_SCHEMA_VERSIONS:
        supported = ", ".join(str(v) for v in sorted(SUPPORTED_SCHEMA_VERSIONS))
        raise VolunteerProfileError("version", f"unsupported schema version {value}; this build accepts {supported}")
    return value


def _load_string_tuple(raw: dict[str, Any], field: str) -> tuple[str, ...]:
    if field not in raw:
        return ()
    value = raw[field]
    if not isinstance(value, list):
        raise VolunteerProfileError(field, f"expected a list, got {type(value).__name__}")
    raw_list = cast("list[Any]", value)
    for i, entry in enumerate(raw_list):
        if not isinstance(entry, str):
            raise VolunteerProfileError(f"{field}[{i}]", f"expected a string, got {type(entry).__name__}")
    return tuple(cast("list[str]", value))


def _load_int_mapping(raw: dict[str, Any], field: str) -> Mapping[str, int]:
    if field not in raw:
        return {}
    value = raw[field]
    if not isinstance(value, dict):
        raise VolunteerProfileError(field, f"expected an object, got {type(value).__name__}")
    raw_dict = cast("dict[Any, Any]", value)
    for k, v in raw_dict.items():
        if not isinstance(k, str):
            raise VolunteerProfileError(f"{field}[{k}]", f"expected a string key, got {type(k).__name__}")
        if not isinstance(v, int) or isinstance(v, bool):
            raise VolunteerProfileError(f"{field}[{k}]", f"expected an integer, got {type(v).__name__}")
    return dict(cast("dict[str, int]", value))


def _load_optional_int(raw: dict[str, Any], field: str) -> int | None:
    if field not in raw:
        return None
    value = raw[field]
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise VolunteerProfileError(field, f"expected an integer, got {type(value).__name__}")
    return value


def _load_extensions(raw: dict[str, Any]) -> Mapping[str, Any]:
    known = {
        "version",
        "allowed_projects",
        "allowed_licenses",
        "task_types",
        "size_caps",
        "adapters_models",
        "cpu_ceiling",
        "ram_ceiling",
        "gpu_ceiling",
        "max_wall_clock_minutes",
        "token_budget",
        "egress_policy",
    }
    return {k: v for k, v in raw.items() if k not in known}
