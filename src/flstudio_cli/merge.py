"""Conservative three-way Playlist merging, including opaque clip tails."""
from __future__ import annotations

import struct

from .flp import Project
from .timeline import playlist_events, split_records


def clips(project):
    return {ar: split_records(e.data) for ar, e in playlist_events(project)}


def identify(records, base):
    result, pending, unused = {}, [], set(range(len(base)))
    base_ids = [struct.unpack_from('<I', r, 32)[0] if len(r) >= 60 else None for r in base]
    for r in records:
        uid = struct.unpack_from('<I', r, 32)[0] if len(r) >= 60 else None
        if uid is not None and base_ids.count(uid) == 1:
            index = base_ids.index(uid); key = ('base', index)
            if key in result: raise ValueError('Duplicate clip identity in one branch')
            result[key] = r; unused.discard(index)
        else: pending.append(r)
    # Legacy records have no stable instance ID. Match unchanged records first;
    # then accept only a unique same-source record, never a guessed reorder.
    remaining = []
    for r in pending:
        exact = [i for i in unused if base[i] == r]
        if len(exact) == 1:
            index = exact[0]; result[('base', index)] = r; unused.remove(index)
        else: remaining.append(r)
    for r in remaining:
        source = r[4:8]
        candidates = [i for i in unused if base[i][4:8] == source]
        if len(candidates) > 1: raise ValueError('Legacy clip identity is ambiguous; save a modern FL copy before merging')
        if candidates:
            index = candidates[0]; result[('base', index)] = r; unused.remove(index)
        else:
            key = ('added', r)
            if key in result: raise ValueError('Identical added clips need distinct native instance IDs')
            result[key] = r
    return result


def three_value(base, ours, theirs):
    if ours == theirs: return ours, False
    if ours == base: return theirs, False
    if theirs == base: return ours, False
    return None, True


def merge_record(base, ours, theirs):
    value, conflict = three_value(base, ours, theirs)
    if not conflict: return value, []
    if base is None or ours is None or theirs is None or not len(base) == len(ours) == len(theirs):
        return None, ['addition/deletion/layout']
    fields = [('position', 0, 4), ('source', 4, 8), ('length', 8, 12), ('track', 12, 14),
              ('group', 14, 16), ('flags', 16, 24), ('source_window', 24, 32), ('opaque_tail', 32, len(base))]
    merged, failures = bytearray(base), []
    for name, start, end in fields:
        part, conflict = three_value(base[start:end], ours[start:end], theirs[start:end])
        if conflict: failures.append(name)
        else: merged[start:end] = part
    return (None, failures) if failures else (bytes(merged), [])


def merge(base, ours, theirs):
    def other(project):
        return (project.format, project.ppq, project.channel_count,
                [e.encode() for e in project.events if e.id != 233])
    _, conflict = three_value(other(base), other(ours), other(theirs))
    if conflict:
        return None, [{'scope': 'non_playlist', 'message': 'Both branches changed other project events differently'}]
    template = theirs if other(ours) == other(base) else ours
    output = Project(template.encode())
    b, a, c = clips(base), clips(ours), clips(theirs)
    merged, conflicts = {}, []
    for arrangement in sorted(b.keys() | a.keys() | c.keys()):
        original = b.get(arrangement, [])
        left, right = identify(a.get(arrangement, []), original), identify(c.get(arrangement, []), original)
        baseline = {('base', i): r for i, r in enumerate(original)}
        rows = []
        for key in baseline.keys() | left.keys() | right.keys():
            record, failed = merge_record(baseline.get(key), left.get(key), right.get(key))
            if failed:
                conflicts.append({'arrangement': arrangement, 'clip': key[1] if key[0] == 'base' else 'added', 'fields': failed})
            elif record is not None: rows.append(record)
        # Concurrent additions can consume the same next ID in each branch.
        # Reassign only a colliding addition, retaining all original clip IDs.
        ids = set(); next_id = max((struct.unpack_from('<I', r, 32)[0] for r in rows if len(r) >= 60), default=0) + 1
        unique = []
        for r in sorted(rows, key=lambda r: (struct.unpack_from('<I', r)[0], r)):
            if len(r) >= 60:
                uid = struct.unpack_from('<I', r, 32)[0]
                if uid in ids:
                    data = bytearray(r); struct.pack_into('<I', data, 32, next_id); r = bytes(data); uid = next_id; next_id += 1
                ids.add(uid)
            unique.append(r)
        merged[arrangement] = b''.join(unique)
    if conflicts: return None, conflicts
    events = dict(playlist_events(output))
    if set(merged) - set(events): return None, [{'scope': 'arrangements', 'message': 'New arrangement containers must be created before merging'}]
    for arrangement, data in merged.items(): events[arrangement].data = data
    return output, []


def register(group, emit, json_option):
    import click
    from pathlib import Path
    from .contracts import Result

    @group.command('merge')
    @click.option('--base', required=True, type=click.Path(path_type=Path))
    @click.option('--ours', required=True, type=click.Path(path_type=Path))
    @click.option('--theirs', required=True, type=click.Path(path_type=Path))
    @click.option('--output', required=True, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @json_option
    def combine(base, ours, theirs, output, dry_run):
        doc, conflicts = merge(Project.read(base), Project.read(ours), Project.read(theirs))
        if conflicts:
            emit(Result(command='project merge', status='rejected', reason_code='merge_conflicts', data={'conflicts': conflicts}))
            raise click.exceptions.Exit(2)
        data = {'output': str(output.resolve()), 'clip_count': len(doc.playlist()), 'scope': 'playlist_three_way', 'live_applied': False}
        if dry_run:
            data.update(file_effects=[], applied_count=None)
            emit(Result(command='project merge', status='planned', data=data)); return
        doc.save(output)
        if Project.read(output).playlist() != doc.playlist(): raise ValueError('Merged playlist readback differs')
        emit(Result(command='project merge', status='artifact_ready', verified_scopes=['saved_playlist_merge'], data=data))
