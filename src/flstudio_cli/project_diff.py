"""A semantic project difference from the same objects exposed by inspect."""
from __future__ import annotations


def compare(before, after, *, details=False):
    changes = []
    def record(section, target, left, right):
        if left == right:
            return
        item = {'section': section, 'target': target,
                'change': 'added' if left is None else 'removed' if right is None else 'modified'}
        if details:
            item.update(before=left, after=right)
        elif isinstance(left, list) or isinstance(right, list):
            item.update(before_count=len(left or []), after_count=len(right or []))
        changes.append(item)

    for field in ('tempo_bpm', 'ppq', 'producer_version'):
        record('project', field, before.get(field), after.get(field))
    record('project', 'metadata', before.get('metadata'), after.get('metadata'))
    record('markers', 'timeline', before.get('markers'), after.get('markers'))
    for section, key in (('arrangements', 'index'), ('controllers', 'pattern_number'), ('channel_settings', 'channel')):
        a = {value[key]: value for value in before.get(section, [])}
        b = {value[key]: value for value in after.get(section, [])}
        for ident in sorted(a.keys() | b.keys()): record(section, ident, a.get(ident), b.get(ident))
    for section, key in (('channels', 'iid'), ('mixer', 'index'), ('automation', 'channel_iid')):
        a = {value[key]: value for value in before[section]}
        b = {value[key]: value for value in after[section]}
        for ident in sorted(a.keys() | b.keys()):
            record(section, ident, a.get(ident), b.get(ident))
    a = {value['number']: value for value in before['patterns']}
    b = {value['number']: value for value in after['patterns']}
    for number in sorted(a.keys() | b.keys()):
        left, right = a.get(number), b.get(number)
        record('patterns', number, {k: v for k, v in left.items() if k not in ('notes', 'note_count')} if left else None,
               {k: v for k, v in right.items() if k not in ('notes', 'note_count')} if right else None)
        note_a, note_b = {}, {}
        for note in (left or {}).get('notes', []):
            note_a.setdefault(note['channel_iid'], []).append(note)
        for note in (right or {}).get('notes', []):
            note_b.setdefault(note['channel_iid'], []).append(note)
        for iid in sorted(note_a.keys() | note_b.keys()):
            record('notes', {'pattern_number': number, 'channel_iid': iid}, note_a.get(iid), note_b.get(iid))
    def clip_key(clip):
        return clip['arrangement'], clip.get('instance_id') if clip.get('instance_id') is not None else clip['clip_index']
    a, b = ({clip_key(clip): {k: v for k, v in clip.items() if k != 'clip_index'} for clip in project.get('playlist', [])}
            for project in (before, after))
    for key in sorted(a.keys() | b.keys()):
        record('playlist', {'arrangement': key[0], 'instance_id': key[1]}, a.get(key), b.get(key))
    return {'equal': not changes, 'change_count': len(changes), 'changes': changes,
            'scope': 'Parsed project objects; unknown plugin state is compared by its existing inspect identity'}


def register(project_group, emit, json_option):
    from pathlib import Path
    import click
    from .flp import Project
    from .contracts import Result

    @project_group.command('diff')
    @click.option('--before', required=True, type=click.Path(path_type=Path))
    @click.option('--after', required=True, type=click.Path(path_type=Path))
    @click.option('--details', is_flag=True, help='Include before/after objects, rather than summaries.')
    @json_option
    def diff(before, after, details):
        a, b = Project.read(before).inspect(include_settings=True), Project.read(after).inspect(include_settings=True)
        emit(Result(command='project diff', status='verified', verified_scopes=['saved_semantic_diff'],
                    data=compare(a, b, details=details)))
