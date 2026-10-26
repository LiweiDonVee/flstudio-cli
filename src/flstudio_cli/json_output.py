"""One strict canonical UTF-8 JSON representation for output and hashing."""

import json
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .contracts import Result


class JsonValueError(ValueError):
    def __init__(self, path: str, message: str):
        self.path = path
        super().__init__(f"{path}: {message}")


def field_path(parts: tuple | list, root: str = "$") -> str:
    path = root
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        elif str(part).isidentifier():
            path += f".{part}"
        else:
            path += f"[{json.dumps(str(part), ensure_ascii=False)}]"
    return path


def _normalize(value: Any, path: str) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise JsonValueError(path, "unpaired Unicode surrogate") from exc
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise JsonValueError(path, "number must be finite")
        return 0 if value == 0 else value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        output = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise JsonValueError(path, "object keys must be strings")
            _normalize(key, path)
            output[key] = _normalize(child, field_path([key], path))
        return output
    if isinstance(value, (list, tuple)):
        return [_normalize(child, f"{path}[{index}]") for index, child in enumerate(value)]
    raise JsonValueError(path, f"unsupported JSON value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(_normalize(value, "$"), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def encode_result(result: Result) -> str:
    return canonical_json(result)


def decode_json(text: str) -> Any:
    def unique_object(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise JsonValueError("$", f"duplicate object key: {key}")
            obj[key] = value
        return obj

    try:
        value = json.loads(text, object_pairs_hook=unique_object)
        # Validate without changing input types before request validation.
        _normalize(value, "$")
    except JsonValueError:
        raise
    except json.JSONDecodeError as exc:
        raise JsonValueError("$", f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    except RecursionError as exc:
        raise JsonValueError("$", "JSON nesting exceeds supported depth") from exc
    except ValueError as exc:
        raise JsonValueError("$", "JSON numeric value exceeds parser limits") from exc
    return value
