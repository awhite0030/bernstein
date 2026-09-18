import json
import pytest
from typing import Any

from bernstein.core.volunteer.profile import (
    DonorProfile,
    VolunteerProfileError,
    load_profile,
)


def test_load_valid_profile() -> None:
    data: dict[str, Any] = {
        "version": 1,
        "allowed_projects": ["https://github.com/foo/bar"],
        "allowed_licenses": ["MIT"],
        "task_types": ["pytest"],
        "size_caps": {"lines": 100},
        "adapters_models": ["gpt-4"],
        "cpu_ceiling": 4,
        "ram_ceiling": 16,
        "gpu_ceiling": 0,
        "max_wall_clock_minutes": 60,
        "token_budget": 1000,
        "egress_policy": ["api.openai.com"],
        "extra_field": "value",
    }
    profile = load_profile(json.dumps(data))

    assert profile.version == 1
    assert profile.allowed_projects == ("https://github.com/foo/bar",)
    assert profile.allowed_licenses == ("MIT",)
    assert profile.task_types == ("pytest",)
    assert profile.size_caps == {"lines": 100}
    assert profile.adapters_models == ("gpt-4",)
    assert profile.cpu_ceiling == 4
    assert profile.ram_ceiling == 16
    assert profile.gpu_ceiling == 0
    assert profile.max_wall_clock_minutes == 60
    assert profile.token_budget == 1000
    assert profile.egress_policy == ("api.openai.com",)
    assert profile.extensions == {"extra_field": "value"}


def test_load_profile_invalid_json() -> None:
    with pytest.raises(VolunteerProfileError) as exc_info:
        load_profile("not json")
    assert exc_info.value.field == "<document>"


def test_load_profile_missing_version() -> None:
    with pytest.raises(VolunteerProfileError) as exc_info:
        load_profile("{}")
    assert exc_info.value.field == "version"


def test_load_profile_invalid_version() -> None:
    with pytest.raises(VolunteerProfileError) as exc_info:
        load_profile('{"version": 999}')
    assert exc_info.value.field == "version"


def test_load_profile_invalid_tuple() -> None:
    with pytest.raises(VolunteerProfileError) as exc_info:
        load_profile('{"version": 1, "allowed_projects": "not a list"}')
    assert exc_info.value.field == "allowed_projects"


def test_load_profile_invalid_tuple_entry() -> None:
    with pytest.raises(VolunteerProfileError) as exc_info:
        load_profile('{"version": 1, "allowed_projects": [123]}')
    assert exc_info.value.field == "allowed_projects[0]"


def test_load_profile_invalid_mapping() -> None:
    with pytest.raises(VolunteerProfileError) as exc_info:
        load_profile('{"version": 1, "size_caps": "not a mapping"}')
    assert exc_info.value.field == "size_caps"


def test_load_profile_invalid_mapping_value() -> None:
    with pytest.raises(VolunteerProfileError) as exc_info:
        load_profile('{"version": 1, "size_caps": {"lines": "not an int"}}')
    assert exc_info.value.field == "size_caps[lines]"
