"""Compact, stable project context for long-running Agents."""
from __future__ import annotations

from collections import Counter
import hashlib
import json

from .automation import read_all
from .fields import arrangements
from .flp import Project

FOCUS = ("project", "channels", "patterns", "playlist", "mixer", "automation", "arrangements")


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
        # Keep identity/counts first, then drop the least useful expanded data
        # until the envelope fits. The omitted list tells the next Agent what
        # to request explicitly in a follow-up.
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
    @json_option
    def command(source, focus, detail, limit, budget):
        """Emit compact context for a long-running Agent session."""
        selected = focus or FOCUS
        emit(Result(command="project snapshot", status="verified",
                    verified_scopes=["saved_project_overview"],
                    data=snapshot(Project.read(source), detail=detail, limit=limit,
                                  focus=selected, budget=budget)))
