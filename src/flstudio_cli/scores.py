"""Transform raw note records without dropping articulation or other channels."""
from __future__ import annotations

import math
import random
import struct

from .flp import NOTE, _ordered_notes


def transform(project, spec):
    allowed = {'pattern_number', 'channel_index', 'note_indices', 'operations'}
    if not isinstance(spec, dict) or set(spec) - allowed or not {'pattern_number', 'operations'} <= set(spec):
        raise ValueError('Transform requires pattern_number, operations and optional channel_index/note_indices')
    number, operations = spec['pattern_number'], spec['operations']
    if not isinstance(operations, list) or not operations: raise ValueError('Operations must be a nonempty array')
    if number not in project.patterns(): raise ValueError('Pattern is absent')
    channel = spec.get('channel_index'); iid = None
    if channel is not None:
        if type(channel) is not int or not 0 <= channel < len(project.channels()): raise ValueError('Channel index is absent')
        iid = project.channels()[channel]['iid']
    indices = spec.get('note_indices')
    if indices is not None and (not isinstance(indices, list) or any(type(i) is not int or i < 0 for i in indices)):
        raise ValueError('note_indices must be nonnegative pattern-wide indices')
    wanted = set(indices) if indices is not None else None
    current, blocks, rows = None, [], []
    for event in project.events:
        if event.id == 65: current = int.from_bytes(event.data, 'little')
        elif event.id in (64, 99): current = None
        elif event.id == 224 and current == number:
            blocks.append(event)
            for raw in NOTE.iter_unpack(event.data):
                rows.append(list(raw))
    chosen = [i for i, row in enumerate(rows) if (iid is None or row[2] == iid) and (wanted is None or i in wanted)]
    if wanted is not None and wanted - set(range(len(rows))): raise ValueError('Note index is absent')
    fields = {'key': 4, 'flags': 1, 'group': 5, 'fine_pitch': 6, 'reserved_raw': 7, 'release': 8,
              'midi_channel': 9, 'pan': 10, 'velocity': 11, 'mod_x': 12, 'mod_y': 13}
    def integer(value, name):
        if type(value) is not int: raise ValueError(name + ' must be an integer')
        return value
    for operation in operations:
        if not isinstance(operation, dict) or 'op' not in operation: raise ValueError('Each transform requires op')
        op = operation['op']
        valid = {'transpose': {'semitones'}, 'shift': {'ticks'}, 'scale': {'factor'},
                 'quantize': {'grid_tick', 'lengths'}, 'reverse': {'start_tick', 'end_tick'},
                 'invert': {'axis_key'}, 'humanize': {'seed', 'velocity', 'timing_tick'}, 'set': {'values'}}
        if op not in valid or set(operation) - (valid[op] | {'op'}): raise ValueError('Unknown note operation/option')
        required = {'transpose': {'semitones'}, 'shift': {'ticks'}, 'scale': {'factor'}, 'quantize': {'grid_tick'},
                    'humanize': {'seed'}, 'set': {'values'}}.get(op, set())
        if not required <= set(operation): raise ValueError('Missing note operation options: ' + ', '.join(sorted(required - set(operation))))
        if op == 'reverse':
            start = integer(operation.get('start_tick', 0), 'start_tick')
            end = integer(operation.get('end_tick', max((rows[i][0] + rows[i][3] for i in chosen), default=start)), 'end_tick')
        if op == 'humanize':
            if 'seed' not in operation: raise ValueError('Humanize requires an explicit seed')
            rng = random.Random(integer(operation['seed'], 'seed'))
            velocity = integer(operation.get('velocity', 0), 'velocity')
            timing = integer(operation.get('timing_tick', 0), 'timing_tick')
            if min(velocity, timing) < 0: raise ValueError('Humanize ranges cannot be negative')
        for index in chosen:
            row = rows[index]
            if op == 'transpose': row[4] += integer(operation['semitones'], 'semitones')
            elif op == 'shift': row[0] += integer(operation['ticks'], 'ticks')
            elif op == 'invert': row[4] = 2 * integer(operation.get('axis_key', 60), 'axis_key') - row[4]
            elif op == 'scale':
                factor = operation['factor']
                if type(factor) not in (int, float) or not math.isfinite(factor) or factor <= 0: raise ValueError('Scale factor must be finite and positive')
                row[0], row[3] = math.floor(row[0] * factor + .5), max(1, math.floor(row[3] * factor + .5))
            elif op == 'quantize':
                grid = integer(operation['grid_tick'], 'grid_tick')
                if grid <= 0: raise ValueError('Quantization grid must be positive')
                row[0] = ((2 * row[0] + grid) // (2 * grid)) * grid
                if operation.get('lengths', False): row[3] = max(grid, ((2 * row[3] + grid) // (2 * grid)) * grid)
            elif op == 'reverse': row[0] = start + end - row[0] - row[3]
            elif op == 'humanize':
                row[11] = max(0, min(127, row[11] + rng.randint(-velocity, velocity)))
                row[0] = max(0, row[0] + rng.randint(-timing, timing))
            elif op == 'set':
                values = operation['values']
                if not isinstance(values, dict) or set(values) - (set(fields) | {'slide'}): raise ValueError('Unknown note property')
                for name, value in values.items():
                    if name == 'slide':
                        if type(value) is not bool: raise ValueError('slide must be boolean')
                        row[1] = row[1] | 8 if value else row[1] & ~8
                    else: row[fields[name]] = integer(value, name)
            if not 0 <= row[0] <= 0xffffffff or not 1 <= row[3] <= 0xffffffff or not 0 <= row[4] <= 131:
                raise ValueError('Transform leaves FL note/time range')
            if not 0 <= row[11] <= 127: raise ValueError('Velocity must be 0..127')
            try: NOTE.pack(*row)
            except struct.error as error: raise ValueError(str(error)) from None
    # Consolidate only this pattern's note blobs; every record retains its own
    # flags/reserved bytes and other channels stay byte-identical.
    if blocks:
        blocks[0].data = _ordered_notes(b''.join(NOTE.pack(*row) for row in rows))
        for event in blocks[1:]: event.data = b''
    return {'pattern_number': number, 'channel_index': channel, 'selected_count': len(chosen), 'operations': operations}


def register(group, emit, json_option):
    import click
    from pathlib import Path
    from .flp import Project
    from .contracts import Result
    from .json_output import decode_json

    @group.command('transform')
    @click.option('--project', required=True, type=click.Path(path_type=Path))
    @click.option('--request', required=True, type=click.Path(path_type=Path))
    @click.option('--output', required=True, type=click.Path(path_type=Path))
    @click.option('--dry-run', is_flag=True)
    @json_option
    def apply(project, request, output, dry_run):
        doc = Project.read(project); result = transform(doc, decode_json(request.read_text(encoding='utf-8-sig')))
        result.update(output=str(output.resolve()), live_applied=False)
        if dry_run:
            result.update(file_effects=[], applied_count=None)
            emit(Result(command='notes transform', status='planned', data=result)); return
        doc.save(output)
        if Project.read(output).patterns() != doc.patterns(): raise ValueError('Transformed score readback differs')
        emit(Result(command='notes transform', status='artifact_ready', verified_scopes=['saved_notes'], data=result))
