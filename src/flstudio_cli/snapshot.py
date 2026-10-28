"""Compact, stable project context for long-running Agents."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import hashlib
import json

from .automation import read_all
from .fields import arrangements
from .flp import Project

FOCUS = ("project", "channels", "patterns", "playlist", "mixer", "automation", "arrangements")
SNAPSHOT_KIND = "flstudio.project.snapshot"


def _clip_sample(clips, limit):
    fields = ("arrangement", "clip_index", "kind", "track", "channel_index", "pattern_number",
              "start_tick", "length_tick", "source_window", "gain", "muted", "record_bytes")
    return [{key: clip[key] for key in fields if key in clip} for clip in clips[:limit]]


def _build(project: Project, *, detail: bool, limit: int) -> dict:
    channels = project.channels()
    patterns = project.patterns()
    playlist = project.playlist()
    mixer = project.mixer()
    curves = read_all(project)
    arrangement_rows = arrangements(project)
    pattern_rows = []
    note_count = 0
    for number, pattern in sorted(patterns.items()):
        notes = pattern.get("notes", [])
        note_count += len(notes)
        by_channel = Counter(note.get("channel_iid") for note in notes)
        row = {"number": number, "name": pattern.get("name"), "note_count": len(notes)}
        if detail:
            row["channel_note_counts"] = dict(sorted((str(key), value) for key, value in by_channel.items()))
        pattern_rows.append(row)

    channel_rows = [{key: channel.get(key) for key in (
        "index", "iid", "name", "type", "plugin", "mixer_track", "volume_raw", "pan_raw")}
                    for channel in channels]
    mixer_rows = []
    for track in mixer:
        mixer_rows.append({
            **{key: track.get(key) for key in ("index", "name", "routes", "volume_raw", "pan_raw", "muted", "effects_enabled") if key in track},
            "plugins": [plugin.get("name") for plugin in track.get("plugins", [])],
        })
    automation_rows = [{key: curve.get(key) for key in (
        "channel", "channel_iid", "points", "target_addresses", "range_raw") if key in curve}
                       for curve in curves]
    playlist_by_arrangement = Counter(str(clip["arrangement"]) for clip in playlist)
    playlist_by_kind = Counter(clip["kind"] for clip in playlist)
    playlist_by_track = Counter(str(clip["track"]) for clip in playlist)
    return {
        "project": {
            "path": str(project.path) if project.path else None,
            "source_sha256": hashlib.sha256(project.source).hexdigest(),
            "producer_version": project.version, "format": project.format,
            "ppq": project.ppq, "tempo_bpm": project.tempo,
        },
        "counts": {
            "events": len(project.events), "channels": len(channels), "patterns": len(patterns),
            "notes": note_count, "playlist_items": len(playlist), "mixer_tracks": len(mixer),
            "automation_channels": len(curves), "arrangements": len(arrangement_rows),
        },
        "channels": channel_rows[:limit], "patterns": pattern_rows[:limit], "mixer": mixer_rows[:limit],
        "automation": [
            {**{key: row[key] for key in ("channel", "channel_iid", "target_addresses", "range_raw") if key in row},
             **({"point_count": len(row.get("points", []))} if "points" in row else {})}
            for row in automation_rows[:limit]
        ],
        "playlist": {
            "by_arrangement": dict(sorted(playlist_by_arrangement.items(), key=lambda item: int(item[0]))),
            "by_kind": dict(sorted(playlist_by_kind.items())),
            "by_track": dict(sorted(playlist_by_track.items(), key=lambda item: int(item[0]))),
        },
        "arrangements": [{"index": row.get("index"), "name": row.get("name"),
                          "track_count": len(row.get("tracks", []))} for row in arrangement_rows[:limit]],
        "truncated": {name: max(0, len(rows) - limit) for name, rows in (
            ("channels", channel_rows), ("patterns", pattern_rows), ("mixer", mixer_rows),
            ("automation", automation_rows), ("arrangements", arrangement_rows))},
    } | ({"playlist_detail": {"samples": _clip_sample(playlist, limit)}} if detail else {})


def snapshot(project: Project, *, detail: bool = False, limit: int = 32,
             focus: tuple[str, ...] = FOCUS, budget: int | None = None) -> dict:
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("snapshot limit must be 1..200")
    selected = list(dict.fromkeys(focus))
    unknown = set(selected) - set(FOCUS)
    if unknown:
        raise ValueError("Unknown snapshot focus: " + ", ".join(sorted(unknown)))
    data = _build(project, detail=detail, limit=limit)
    omitted = [name for name in FOCUS[1:] if name not in selected]
    for name in omitted:
        data.pop(name, None)
    data["context"] = {"focus": selected, "omitted": omitted, "detail": detail, "limit": limit}
    if budget is not None:
        if type(budget) is not int or not 2000 <= budget <= 1000000:
            raise ValueError("snapshot budget must be 2000..1000000 characters")
        drop_order = ["playlist_detail"] + [name for name in ("playlist", "automation", "patterns", "mixer", "channels", "arrangements") if name not in selected] + [name for name in ("playlist", "automation", "patterns", "mixer", "channels", "arrangements") if name in selected]
        for name in drop_order:
            if len(json.dumps(data, ensure_ascii=False, separators=(",", ":"))) <= budget:
                break
            if name in data:
                data.pop(name)
                data["context"]["omitted"].append(name)
        data["context"]["budget"] = budget
        data["context"]["budget_exceeded"] = len(json.dumps(data, ensure_ascii=False, separators=(",", ":"))) > budget
    return data


def _snapshot_file(path: Path) -> dict:
    from .json_output import decode_json
    try:
        raw = decode_json(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Invalid snapshot file: {path}: {exc}") from None
    if isinstance(raw, dict) and raw.get("kind") == SNAPSHOT_KIND and isinstance(raw.get("snapshot"), dict):
        return raw["snapshot"]
    if isinstance(raw, dict) and raw.get("command") == "project snapshot" and isinstance(raw.get("data"), dict):
        return raw["data"]
    if isinstance(raw, dict) and isinstance(raw.get("current"), dict):
        return raw["current"]
    if isinstance(raw, dict) and isinstance(raw.get("project"), dict) and isinstance(raw.get("counts"), dict):
        return raw
    raise ValueError(f"Snapshot file has an unsupported shape: {path}")


def _row_key(section, row):
    keys = {"channels": "iid", "patterns": "number", "mixer": "index",
            "automation": "channel_iid", "arrangements": "index"}
    key = keys.get(section)
    return row.get(key) if key else None


def compare_snapshots(before: dict, after: dict) -> dict:
    """Compare two bounded snapshots without pretending omitted sections are equal."""
    comparable, unknown, changes = [], [], []
    sections = ("project", "counts", "channels", "patterns", "playlist", "mixer", "automation", "arrangements")
    before_omitted = set(before.get("context", {}).get("omitted", []))
    after_omitted = set(after.get("context", {}).get("omitted", []))
    for section in sections:
        if section not in before or section not in after or section in before_omitted or section in after_omitted:
            unknown.append(section)
            continue
        comparable.append(section)
        left, right = before[section], after[section]
        if isinstance(left, list) and isinstance(right, list):
            left_rows = {_row_key(section, row): row for row in left if _row_key(section, row) is not None}
            right_rows = {_row_key(section, row): row for row in right if _row_key(section, row) is not None}
            for key in sorted(left_rows.keys() | right_rows.keys(), key=lambda value: str(value)):
                old, new = left_rows.get(key), right_rows.get(key)
                if old != new:
                    changes.append({"section": section, "key": key,
                                    "change": "added" if old is None else "removed" if new is None else "modified",
                                    "before": old, "after": new})
        elif left != right:
            changes.append({"section": section, "change": "modified", "before": left, "after": right})
    source_before = before.get("project", {}).get("source_sha256")
    source_after = after.get("project", {}).get("source_sha256")
    return {
        "equal": not changes,
        "complete": not unknown,
        "source_changed": source_before != source_after,
        "from": {"source_sha256": source_before, "path": before.get("project", {}).get("path")},
        "to": {"source_sha256": source_after, "path": after.get("project", {}).get("path")},
        "compared_sections": comparable,
        "unknown_sections": sorted(set(unknown)),
        "change_count": len(changes),
        "changes": changes[:128],
        "changes_truncated": max(0, len(changes) - 128),
    }


def write_snapshot(path: Path, data: dict) -> Path:
    from .json_output import canonical_json
    path = path.resolve()
    if path.exists() or not path.parent.is_dir():
        raise ValueError("Choose a new snapshot path with an existing parent")
    payload = {"kind": SNAPSHOT_KIND, "schema_version": 1, "snapshot": data}
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8", newline="\n")
    return path


def register(project_group, emit, json_option):
    from pathlib import Path
    import click
    from .contracts import Result

    @project_group.command("snapshot")
    @click.option("--input", "source", required=True, type=click.Path(path_type=Path))
    @click.option("--focus", multiple=True, type=click.Choice(FOCUS), help="Sections to expand; repeat to combine.")
    @click.option("--detail", is_flag=True, help="Include bounded note/Playlist detail samples.")
    @click.option("--limit", type=click.IntRange(1, 200), default=32, show_default=True)
    @click.option("--budget", type=click.IntRange(2000, 1000000), help="Maximum approximate JSON characters.")
    @click.option("--output", type=click.Path(path_type=Path), help="Save a reusable snapshot baseline; the path must be new.")
    @click.option("--since", type=click.Path(path_type=Path), help="Compare against a snapshot baseline and return only the bounded delta.")
    @json_option
    def command(source, focus, detail, limit, budget, output, since):
        """Emit compact context, optionally saving or comparing a baseline."""
        selected = focus or FOCUS
        current = snapshot(Project.read(source), detail=detail, limit=limit,
                           focus=selected, budget=budget)
        response = current
        if since:
            response = {"current": current, "delta": compare_snapshots(_snapshot_file(since), current)}
        if output:
            written = write_snapshot(output, current)
            response = {**response, "snapshot_file": str(written)}
        emit(Result(command="project snapshot", status="artifact_ready" if output else "verified",
                    verified_scopes=["saved_project_overview"] + (["snapshot_file"] if output else []), data=response))
