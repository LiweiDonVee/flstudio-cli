"""Pure planning over supplied observations. There is deliberately no executor."""

import hashlib
from pathlib import Path
import re

from .contracts import NotesReplaceRequest, Plan, Result
from .json_output import canonical_json


class PlanningError(ValueError):
    pass


def build_plan(request: NotesReplaceRequest, source_probe: Result) -> Plan:
    data = source_probe.data
    if (source_probe.status not in ("partial", "verified")
            or "flp_container" not in source_probe.verified_scopes
            or data.get("parse_scope") != "container"
            or not isinstance(data.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", data["sha256"])
            or not isinstance(data.get("path"), str)
            or Path(data["path"]) != request.project):
        raise PlanningError("a validated container snapshot of the requested project is required")
    return Plan(request=request, request_sha256=hashlib.sha256(canonical_json(request).encode("utf-8")).hexdigest(),
                source_sha256=data["sha256"], requested_count=len(request.notes),
                unmet_requirements=["score.semantic_read", "target.resolve", "notes.replace", "project.persistence_verify"],
                effects=["live_score_replace", "project_persistence"])
