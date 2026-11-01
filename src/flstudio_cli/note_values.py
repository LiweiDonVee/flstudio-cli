"""The note input bounds shared by JSON contracts and binary score editing."""

# default, minimum, maximum; Ellipsis denotes a required field.
FIELDS = {
    'key': (..., 0, 131), 'start_tick': (..., 0, 0xffffffff),
    'length_tick': (..., 1, 0xffffffff), 'velocity': (..., 0, 127),
    'flags': (0x4000, 0, 65535), 'group': (0, 0, 65535),
    'fine_pitch': (120, 0, 255), 'reserved_raw': (0, 0, 255),
    'release': (64, 0, 255), 'midi_channel': (0, 0, 255),
    'pan': (64, 0, 255), 'mod_x': (128, 0, 255), 'mod_y': (128, 0, 255),
}

ARTICULATION={'slide':('flags',8),'porta':('midi_channel',16),'muted':('midi_channel',32)}


def normalize_articulation(note):
    """Named properties modify only their own bits, retaining raw compatibility."""
    if not isinstance(note,dict):return note
    note=dict(note)
    for name,(field,mask) in ARTICULATION.items():
        value=note.pop(name,None)
        if value is None:continue
        if type(value) is not bool:raise ValueError(f'{name} must be boolean')
        current=note.get(field,FIELDS[field][0])
        if type(current) is not int:raise ValueError(f'{field} must be integer')
        note[field]=current|mask if value else current&~mask
    color=note.pop('color',None)
    if color is not None:
        if type(color) is not int or not 0<=color<=15:raise ValueError('color must be integer 0..15')
        current=note.get('midi_channel',0)
        if type(current) is not int:raise ValueError('midi_channel must be integer')
        note['midi_channel']=(current&~15)|color
    return note


def articulation(note):
    return {**{name:bool(note.get(field,FIELDS[field][0])&mask) for name,(field,mask) in ARTICULATION.items()},
            'color':note.get('midi_channel',0)&15}


def validate(note):
    note=normalize_articulation(note)
    if not isinstance(note, dict) or note.keys() - FIELDS.keys():
        raise ValueError('Note requires an object with known fields')
    values = {}
    for name, (default, low, high) in FIELDS.items():
        value = note.get(name, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'Note {name} must be an integer {low}..{high}')
        values[name] = value
    return values
