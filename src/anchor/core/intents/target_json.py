"""Copy opaque host targets without accepting non-JSON or non-finite values."""
from __future__ import annotations

import math
from copy import deepcopy
from typing import Any, cast

from pydantic import JsonValue

from anchor.core.intents.errors import ThreadError


def copy_json_targets(raw: Any) -> list[JsonValue]:
    """Validate after the host's codec, then detach its mutable JSON values."""
    visiting: set[int] = set()

    def valid(value: Any) -> bool:
        if value is None or isinstance(value, (str, bool, int)):
            return True
        if isinstance(value, float):
            return math.isfinite(value)
        if not isinstance(value, (list, dict)) or id(value) in visiting:
            return False
        visiting.add(id(value))
        try:
            if isinstance(value, list):
                return all(valid(item) for item in value)
            return all(isinstance(key, str) and valid(item) for key, item in value.items())
        finally:
            visiting.remove(id(value))

    if not isinstance(raw, list) or not valid(raw):
        raise ThreadError("invalid_targets", "host targets must be JSON values with finite numbers")
    return cast(list[JsonValue], deepcopy(raw))
