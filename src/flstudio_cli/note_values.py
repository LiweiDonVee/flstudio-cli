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


def validate(note):
    if not isinstance(note, dict) or note.keys() - FIELDS.keys():
        raise ValueError('Note requires an object with known fields')
    values = {}
    for name, (default, low, high) in FIELDS.items():
        value = note.get(name, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'Note {name} must be an integer {low}..{high}')
        values[name] = value
    return values
