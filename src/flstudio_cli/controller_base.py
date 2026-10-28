# name=FLStudioCLI
"""Standalone FL MIDI-script entry point. The CLI communicates through files."""
import math
import channels
import mixer
import patterns
import playlist
import transport
import general
import arrangement
import plugins
import ui
import midi
import device

_CLI_FILE_RPC = True
_CLI_CONTROLLER_DIR = None
_HANDLERS = {}


def tempo():
    value = mixer.getCurrentTempo()
    return value / 1000 if value > 999 else float(value)


def index(value, count):
    if type(value) is not int or not 0 <= value < count:
        raise ValueError('Index is outside the current global object range')
    return value


def color_out(value):
    return '#%02X%02X%02X' % (value & 255, (value >> 8) & 255, (value >> 16) & 255)


def color_in(value):
    if isinstance(value, str) and len(value) == 7 and value.startswith('#'):
        red, green, blue = (int(value[i:i + 2], 16) for i in (1, 3, 5))
        return red | green << 8 | blue << 16
    if type(value) is int: return value
    raise ValueError('Color requires #RRGGBB or a native integer')


def volume(norm, db):
    return {'vol_norm': round(norm, 6), 'silent': norm <= 0,
            'vol_db': (0.0 if abs(db) < .0001 else round(db, 4)) if math.isfinite(db) else None}


def normalized(params, anchor=1.0):
    value = params.get('db', params.get('value'))
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Volume must be a finite number')
    if 'db' in params or params.get('unit') == 'db':
        # Invert FL's documented VolTodB curve before its display rounding.
        # Mixer unity is .8; channel unity is 1.0.
        value = anchor * math.log1p(10 * 10 ** (value / 20)) / math.log(11)
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('Normalized value must be finite 0..1')
    return value


def page(total, params, function, key):
    start = max(0, int(params.get('start', 0))); stop = min(total, start + int(params.get('limit', 128)))
    return {'total': total, 'start': start, 'next_start': stop if stop < total else None,
            key: [function(i) for i in range(start, stop)]}


def track_info(i):
    index(i, mixer.trackCount())
    return {'i': i, 'name': mixer.getTrackName(i), 'pan': mixer.getTrackPan(i),
            'mute': bool(mixer.isTrackMuted(i)), 'solo': bool(mixer.isTrackSolo(i)),
            'color': color_out(mixer.getTrackColor(i)),
            **volume(mixer.getTrackVolume(i), mixer.getTrackVolume(i, 1))}


def channel_info(i):
    index(i, channels.channelCount(True))
    return {'i': i, 'name': channels.getChannelName(i, True), 'pan': channels.getChannelPan(i, True),
            'mute': bool(channels.isChannelMuted(i, True)), 'solo': bool(channels.isChannelSolo(i, True)),
            'target_fx_track': channels.getTargetFxTrack(i, True),
            'color': color_out(channels.getChannelColor(i, True)),
            **volume(channels.getChannelVolume(i, 0, True), channels.getChannelVolume(i, 1, True))}


def play_state(params=None):
    return {'playing': bool(transport.isPlaying()), 'recording': bool(transport.isRecording())}


def project_state(params=None):
    return {'fl_version': ui.getVersion(), 'tempo_bpm': tempo(), **play_state(),
            'pattern_number': patterns.patternNumber(), 'pattern_count': patterns.patternCount(),
            'channel_count': channels.channelCount(True), 'mixer_track_count': mixer.trackCount()}


def set_tempo(params):
    bpm = params['bpm']
    if type(bpm) not in (int, float) or not math.isfinite(bpm) or not 10 <= bpm <= 999:
        raise ValueError('Tempo must be 10..999 BPM')
    general.processRECEvent(midi.REC_Tempo, round(bpm * 1000), midi.REC_Control | midi.REC_UpdateControl)
    return {'bpm': tempo()}


def song_position(params=None):
    ticks = transport.getSongPos(2)
    return {'position_ms': transport.getSongPos(0), 'position_ticks': ticks,
            'position_beats': ticks / general.getRecPPQ(), 'bpm': tempo()}


def set_position(params):
    if 'ticks' in params: transport.setSongPos(params['ticks'], 2)
    elif 'beats' in params: transport.setSongPos(params['beats'] * general.getRecPPQ(), 2)
    elif 'ms' in params: transport.setSongPos(params['ms'], 0)
    else: raise ValueError('Position requires ticks, beats or ms')
    return song_position()


def play(params):
    if not transport.isPlaying(): transport.start()
    return play_state()


def stop(params):
    if transport.isPlaying(): transport.stop()
    return play_state()


def record(params):
    if bool(params.get('enabled', True)) != bool(transport.isRecording()): transport.record()
    return play_state()


def track_set(params, field):
    track = index(params.get('track', params.get('index', 0)), mixer.trackCount())
    if field == 'volume': mixer.setTrackVolume(track, normalized(params, .8))
    elif field == 'pan': mixer.setTrackPan(track, params['value'])
    elif field == 'name': mixer.setTrackName(track, params['name'])
    elif field == 'color': mixer.setTrackColor(track, color_in(params['color']))
    elif field == 'mute': mixer.muteTrack(track, int(params['muted']))
    return track_info(track)


def channel_set(params, field):
    channel = index(params.get('channel', params.get('index', 0)), channels.channelCount(True))
    if field == 'volume': channels.setChannelVolume(channel, normalized(params), 0, True)
    elif field == 'pan': channels.setChannelPan(channel, params['value'], 0, True)
    elif field == 'name': channels.setChannelName(channel, params['name'], True)
    elif field == 'color': channels.setChannelColor(channel, color_in(params['color']), True)
    elif field == 'mute': channels.muteChannel(channel, int(params['muted']), True)
    elif field == 'routing':
        destination = index(params.get('track', params.get('target')), mixer.trackCount())
        channels.setTargetFxTrack(channel, destination, True)
    return channel_info(channel)


def routing(track):
    index(track, mixer.trackCount())
    return {'track': track, 'name': mixer.getTrackName(track),
            'routes_to': [{'dst': dst, 'dst_name': mixer.getTrackName(dst)} for dst in range(mixer.trackCount())
                          if dst != track and mixer.getRouteSendActive(track, dst)]}


def set_route(params):
    source = index(params['src'], mixer.trackCount()); destination = index(params['dst'], mixer.trackCount())
    mixer.setRouteTo(source, destination, int(params.get('enabled', True))); mixer.afterRoutingChanged()
    return {'src': source, 'dst': destination, 'enabled': bool(mixer.getRouteSendActive(source, destination))}


def plugin_list(params):
    track = index(params.get('track', 0), mixer.trackCount())
    return {'track': track, 'plugins': [{'slot': slot, 'name': plugins.getPluginName(track, slot)}
                                       for slot in range(10) if plugins.isValid(track, slot)]}


def peaks(params):
    tracks = params.get('tracks', list(range(mixer.trackCount())))
    return {'playing': bool(transport.isPlaying()), 'peaks': [{'i': index(i, mixer.trackCount()),
            'left': mixer.getTrackPeaks(i, 0), 'right': mixer.getTrackPeaks(i, 1)} for i in tracks]}


_HANDLERS.update({
    'ping': lambda p: {'alive': True, 'fl_version': ui.getVersion(), 'protocol_version': 2},
    'get_project_state': project_state, 'get_tempo': lambda p: {'bpm': tempo()}, 'set_tempo': set_tempo,
    'get_play_state': play_state, 'play': play, 'stop': stop, 'record': record,
    'get_song_position': song_position, 'set_song_position': set_position,
    'mixer_get_track': lambda p: track_info(p.get('index', 0)),
    'mixer_list_tracks': lambda p: page(mixer.trackCount(), p, track_info, 'tracks'),
    'mixer_get_routing': lambda p: routing(p.get('track', 0)),
    'mixer_get_routing_all': lambda p: page(mixer.trackCount(), p, lambda i: {'i': i, **routing(i)}, 'routing'),
    'mixer_set_route': set_route, 'mixer_get_peaks': peaks,
    'channel_get': lambda p: channel_info(p.get('index', 0)),
    'channel_list': lambda p: page(channels.channelCount(True), p, channel_info, 'channels'),
    'channel_routing_summary': lambda p: page(channels.channelCount(True), p, lambda i:
        {'channel': i, 'name': channels.getChannelName(i, True), 'target_mixer_track': channels.getTargetFxTrack(i, True),
         'target_name': mixer.getTrackName(channels.getTargetFxTrack(i, True))}, 'channels'),
    'plugin_list': plugin_list,
    'plugin_get_params': lambda p: _HANDLERS['cli_plugin_params'](p),
    'plugin_get_param': lambda p: _HANDLERS['cli_plugin_get_param'](p),
    'plugin_set_param': lambda p: _HANDLERS['cli_plugin_set_param'](p),
    'pattern_list': lambda p: page(patterns.patternCount(), p, lambda i:
        {'number': i + 1, 'name': patterns.getPatternName(i + 1)}, 'patterns'),
    'pattern_get_length': lambda p: {'pattern': p.get('number', patterns.patternNumber()),
        'length_steps': patterns.getPatternLength(p.get('number', patterns.patternNumber()))},
})
for _field in ('volume', 'pan', 'name', 'color', 'mute'):
    _HANDLERS['mixer_set_' + _field] = lambda p, f=_field: track_set(p, f)
    _HANDLERS['channel_set_' + _field] = lambda p, f=_field: channel_set(p, f)
_HANDLERS['channel_set_target_fx_track'] = lambda p: channel_set(p, 'routing')


def OnInit():
    print('[FL Studio CLI] standalone controller ready: ' + str(ui.getVersion()))


import importlib.util
import os

# Load the saved helper for each controller reload, rather than reusing a
# cached helper from this or another Hardware directory.
_runtime_spec = importlib.util.spec_from_file_location('_flstudio_cli_runtime',
    os.path.join(_CLI_CONTROLLER_DIR, 'flstudio_cli_extension.py'))
_runtime = importlib.util.module_from_spec(_runtime_spec)
_runtime_spec.loader.exec_module(_runtime)
_runtime.install(_HANDLERS, globals())
