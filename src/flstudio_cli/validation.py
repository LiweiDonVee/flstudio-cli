"""Read-only semantic validation for a saved FL project.

Validation deliberately reuses the same readers used by edit/readback paths. It
does not attempt to repair a file and never writes the source project.
"""
from __future__ import annotations

import hashlib

from .flp import Project


def validate(project: Project) -> dict:
    """Return a compact, agent-friendly validation report."""
    errors: list[dict] = []
    warnings: list[dict] = []

    def error(scope: str, message: str, **extra):
        errors.append({"scope": scope, "message": message, **extra})

    try:
        channels = project.channels()
        patterns = project.patterns()
        playlist = project.playlist()
        mixer = project.mixer()
        from .automation import read_all
        automation = read_all(project)
    except Exception as exc:
        return {
            "valid": False,
            "errors": [{"scope": "decode", "message": str(exc)}],
            "warnings": [],
            "checks": {"envelope": True, "semantic_decode": False, "roundtrip": False},
            "source_sha256": hashlib.sha256(project.source).hexdigest(),
        }

    if project.channel_count != len(channels):
        error("channels", "FLhd channel count disagrees with decoded channels",
              header_count=project.channel_count, decoded_count=len(channels))
    iids = [channel["iid"] for channel in channels]
    if len(iids) != len(set(iids)):
        error("channels", "channel identities are not unique")
    iid_set = set(iids)

    for number, pattern in patterns.items():
        if type(number) is not int or number < 1:
            error("patterns", "pattern number must be positive", pattern=number)
        for index, note in enumerate(pattern.get("notes", [])):
            if note.get("channel_iid") not in iid_set:
                error("notes", "note references an absent channel identity",
                      pattern=number, note=index, channel_iid=note.get("channel_iid"))
            if note.get("channel_index") is None:
                error("notes", "note channel index could not be resolved", pattern=number, note=index)

    mixer_count = len(mixer)
    for track in mixer:
        index = track.get("index")
        for destination in track.get("routes", []):
            if destination == index:
                error("mixer", "track routes to itself", track=index)
            elif type(destination) is not int or not 0 <= destination < mixer_count:
                error("mixer", "route destination is outside the decoded mixer", track=index,
                      destination=destination)

    addresses: dict[int, int] = {}
    for curve in automation:
        for address in curve.get("target_addresses", []):
            owner = addresses.setdefault(address, curve.get("channel_iid"))
            if owner != curve.get("channel_iid"):
                error("automation", "controller address is linked by multiple channels",
                      address=address, first_channel_iid=owner,
                      second_channel_iid=curve.get("channel_iid"))
        previous = -1.0
        for point in curve.get("points", []):
            position = point.get("position_beats")
            if type(position) not in (int, float) or position < previous:
                error("automation", "curve points are not sorted", channel=curve.get("channel"))
                break
            previous = position

    roundtrip = False
    try:
        reparsed = Project(project.encode())
        roundtrip = (
            len(reparsed.events) == len(project.events)
            and reparsed.channel_count == project.channel_count
            and len(reparsed.channels()) == len(channels)
            and len(reparsed.playlist()) == len(playlist)
        )
        if not roundtrip:
            error("roundtrip", "re-encoded project changed decoded structure")
    except Exception as exc:
        error("roundtrip", "re-encoded project could not be parsed", detail=str(exc))

    if project.version == "unknown":
        warnings.append({"scope": "profile", "message": "producer version is unknown; version-specific writers are disabled"})
    if any(clip.get("record_bytes") not in (32, 60, 80, 88, 100, 108, 120, 128) for clip in playlist):
        warnings.append({"scope": "playlist", "message": "playlist contains a record size outside the known profiles"})

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "envelope": True,
            "semantic_decode": True,
            "roundtrip": roundtrip,
            "channel_references": not any(item["scope"] in ("channels", "notes") for item in errors),
            "mixer_routes": not any(item["scope"] == "mixer" for item in errors),
            "automation_links": not any(item["scope"] == "automation" for item in errors),
        },
        "source_sha256": hashlib.sha256(project.source).hexdigest(),
        "producer_version": project.version,
        "counts": {
            "events": len(project.events), "channels": len(channels),
            "patterns": len(patterns), "notes": sum(len(p.get("notes", [])) for p in patterns.values()),
            "playlist": len(playlist), "mixer_tracks": len(mixer), "automation": len(automation),
        },
    }


def register(project_group, emit, json_option):
    from pathlib import Path
    import click
    from .contracts import Result

    @project_group.command("validate")
    @click.option("--input", "source", required=True, type=click.Path(path_type=Path))
    @json_option
    def command(source):
        """Validate a saved project without changing it or starting FL."""
        report = validate(Project.read(source))
        emit(Result(command="project validate", status="verified" if report["valid"] else "failed",
                    reason_code=None if report["valid"] else "project_validation_failed",
                    verified_scopes=["saved_project_structure"] if report["valid"] else [], data=report))
        if not report["valid"]:
            raise click.exceptions.Exit(5)
