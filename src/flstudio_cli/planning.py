"""Pure note-edit planning over an explicitly observed saved score."""

import hashlib
from pathlib import Path
import re

from .contracts import NotesReplaceRequest, Plan, Result
from .json_output import canonical_json


class PlanningError(ValueError):
    pass


def build_plan(request: NotesReplaceRequest, source_probe: Result) -> Plan:
    data = source_probe.data
    if (source_probe.status != 'verified'
            or 'saved_notes' not in source_probe.verified_scopes
            or not isinstance(data.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", data["sha256"])
            or not isinstance(data.get("path"), str)
            or Path(data["path"]) != request.project):
        raise PlanningError("a validated container snapshot of the requested project is required")
    channels = data['channels']
    if request.channel_index >= len(channels):
        raise PlanningError('Channel index is absent from the saved project')
    unmet = [] if request.output is not None else ['output_path']
    return Plan(request=request, request_sha256=hashlib.sha256(canonical_json(request).encode("utf-8")).hexdigest(),
                source_sha256=data["sha256"], requested_count=len(request.notes),
                executable=not unmet, target_resolution='saved_score',
                bound_target={'pattern_number': request.pattern_number, 'channel_index': request.channel_index,
                              'channel_iid': channels[request.channel_index]['iid']},
                unmet_requirements=unmet, effects=['new_saved_project_copy'])
