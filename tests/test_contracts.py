import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError


def test_result_encodes_unicode_and_normalizes_nested_negative_zero():
    from flstudio_cli.contracts import Result
    from flstudio_cli.json_output import encode_result

    result = Result(command="例子", status="unknown", data={"音量": [-0.0, {"值": 0.0}]})
    encoded = encode_result(result)
    assert "音量" in encoded
    assert "-0" not in encoded
    assert json.loads(encoded)["data"]["音量"] == [0, {"值": 0}]


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_encoder_rejects_nonfinite_with_nested_field_path(value):
    from flstudio_cli.contracts import Result
    from flstudio_cli.json_output import JsonValueError, encode_result

    with pytest.raises(JsonValueError, match=r"\$\.data\.notes\[0\]\.velocity"):
        encode_result(Result(command="test", status="planned", data={"notes": [{"velocity": value}]}))


@pytest.mark.parametrize("field,value", [
    ("key", -1), ("key", 128), ("key", 36.0), ("key", True), ("key", "36"),
    ("start_tick", -1), ("length_tick", 0), ("velocity", 0), ("velocity", 128),
    ("length_tick", math.inf), ("start_tick", math.nan),
])
def test_note_input_rejects_invalid_or_coerced_numeric_fields(field, value):
    from flstudio_cli.contracts import NoteInput

    note = dict(key=36, start_tick=0, length_tick=24, velocity=100)
    note[field] = value
    with pytest.raises(ValidationError) as exc:
        NoteInput.model_validate(note)
    assert exc.value.errors()[0]["loc"] == (field,)


def test_request_normalizes_project_path_and_refuses_extra_fields(tmp_path, monkeypatch):
    from flstudio_cli.contracts import NotesReplaceRequest

    monkeypatch.chdir(tmp_path)
    payload = dict(operation="notes.replace", project="歌曲.flp", pattern_number=1, channel_index=0, notes=[])
    request = NotesReplaceRequest.model_validate(payload)
    assert request.project == (tmp_path / "歌曲.flp").resolve()
    assert request.project.is_absolute()
    with pytest.raises(ValidationError):
        NotesReplaceRequest.model_validate({**payload, "implicit_current": True})
    for field, value in [("pattern_number", 0), ("channel_index", -1), ("pattern_number", True)]:
        with pytest.raises(ValidationError):
            NotesReplaceRequest.model_validate({**payload, field: value})


def test_result_defaults_are_independent_and_unknown_cannot_invent_counts():
    from flstudio_cli.contracts import Result

    a = Result(command="a", status="unknown")
    b = Result(command="b", status="unknown")
    a.data["x"] = 1
    a.verified_scopes.append("a")
    assert b.data == {} and b.verified_scopes == []
    with pytest.raises(ValidationError):
        Result(command="a", status="unknown", data={"applied_count": 12})


def test_json_input_rejects_duplicate_keys_and_reports_nonfinite_paths():
    from flstudio_cli.json_output import JsonValueError, decode_json

    for raw in ['{"notes":[{"key":NaN}]}', '{"notes":[{"key":1e999}]}']:
        with pytest.raises(JsonValueError, match=r"\$\.notes\[0\]\.key"):
            decode_json(raw)
    with pytest.raises(JsonValueError, match="duplicate"):
        decode_json('{"key":36,"key":40}')


@pytest.mark.parametrize("value", [True, 1.0, "1"])
def test_schema_version_refuses_coercion(value):
    from flstudio_cli.contracts import Result

    with pytest.raises(ValidationError):
        Result(schema_version=value, command="test", status="verified")
