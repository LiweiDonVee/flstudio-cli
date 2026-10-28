"""FL-side host operations on OnIdle; owned RPC stays in the script sandbox."""
import base64
import json
import math
import os
import time

REVISION = 'flstudio-cli-fullstack-6'
PREFIX = b'\x7dFCL'
PARAM_LABELS = {
    'Emphasizer': {'杈撳叆澧炵泭': '输入增益', '鐢靛钩鍖归厤': '电平匹配',
                   '鏃佽矾': '旁路', '杈撳嚭澧炵泭': '输出增益'},
    'Fruity Balance': {'骞宠　': '平衡', '闊抽噺': '音量'},
}


def install(handlers, namespace=None):
    import channels
    import plugins
    import mixer
    instance = '%x' % time.monotonic_ns()
    owned_directory = os.environ.get('FLSTUDIO_CLI_SESSION_DIR')
    editor_files = bool(namespace and namespace.get('_CLI_FILE_RPC')) and not owned_directory
    file_mode = bool(owned_directory) or editor_files
    render_mode = os.environ.get('FLSTUDIO_CLI_RENDER') == '1'
    cache, jobs, recording_jobs = {}, {}, {}
    format_arity = [None]

    def owner_marker():
        if editor_files: return None
        if channels.channelCount(True):
            name = channels.getChannelName(0, True)
            if name.startswith('__FLCLI_OWNED__:'):
                return name
        if namespace and namespace.get('general'):
            title = namespace['general'].getProjectTitle()
            if title.startswith('__FLCLI_OWNED__:'): return title
        return None

    def target(params):
        item = params.get('target', params)
        if 'channel' in item:
            index, slot, glob = item['channel'], -1, True
            if type(index) is not int or not 0 <= index < channels.channelCount(True):
                raise ValueError('Choose an existing global channel index')
        elif 'track' in item and 'slot' in item:
            index, slot, glob = item['track'], item['slot'], False
            if type(index) is not int or type(slot) is not int or not 0 <= index < mixer.trackCount() or not 0 <= slot < 10:
                raise ValueError('Choose an existing mixer track and slot 0..9')
        else:
            raise ValueError('Plugin target requires channel or track+slot')
        if not plugins.isValid(index, slot, glob):
            raise ValueError('No plugin at the explicit target')
        return index, slot, glob

    def identity(where):
        index, slot, glob = where
        return plugins.getPluginName(index, slot, False, glob), plugins.getParamCount(index, slot, glob)

    def value_string(param, where):
        index, slot, glob = where
        if format_arity[0] == 4:
            return plugins.getParamValueString(param, index, slot, glob) or ''
        try:
            value = plugins.getParamValueString(param, index, slot, 0, glob) or ''
            format_arity[0] = 5
            return value
        except TypeError:
            format_arity[0] = 4
            return plugins.getParamValueString(param, index, slot, glob) or ''

    def param_label(param, where, plugin=None):
        name = plugins.getParamName(param, *where)
        # Only exact Windows labels observed in FL are repaired. A successful
        # codec roundtrip alone would also corrupt valid short Chinese names.
        if name in ('杈撳叆澧炵泭', '鐢靛钩鍖归厤', '鏃佽矾', '杈撳嚭澧炵泭', '骞宠　', '闊抽噺'):
            return PARAM_LABELS.get(plugin or identity(where)[0], {}).get(name, name)
        return name

    def read_param(where, param, display=True):
        index, slot, glob = where
        count = identity(where)[1]
        if type(param) is not int or not 0 <= param < count:
            raise ValueError('Parameter index is out of range')
        return {'i': param, 'name': param_label(param, where),
                'v': round(plugins.getParamValue(param, index, slot, glob), 6),
                's': value_string(param, where) if display else None}

    def names(where):
        name, count = identity(where)
        key = (*where, name, count)
        entry = cache.get(key)
        now = time.monotonic()
        if entry is None or now - entry[0] > 3:
            index, slot, glob = where
            values = [(p, param_label(p, where, name)) for p in range(count)]
            if len(cache) >= 32:
                del cache[next(iter(cache))]
            cache[key] = (now, [(p, n) for p, n in values if n])
        return key, cache[key][1]

    def resolve(where, param):
        if type(param) is int:
            return read_param(where, param, False)
        if not isinstance(param, str) or not param:
            raise ValueError('Parameter must be an index or exact nonempty name')
        _, labels = names(where)
        matches = [p for p, n in labels if n.casefold() == param.casefold()]
        if len(matches) != 1:
            raise ValueError('Parameter name must identify exactly one index; found %d' % len(matches))
        result = read_param(where, matches[0], False)
        if result['name'].casefold() != param.casefold():
            cache.clear()
            raise ValueError('Plugin parameter labels changed; discover again')
        return result

    def info(params):
        where = target(params)
        name, count = identity(where)
        return {'plugin': name, 'total': count, 'location': 'channel' if where[1] < 0 else 'mixer',
                'index': where[0], 'slot': where[1], 'index_scope': 'global'}

    def get_params(params):
        where = target(params)
        name, count = identity(where)
        search = str(params.get('search', '')).casefold()
        start = max(0, int(params.get('start', 0)))
        _, labels = names(where)
        eligible = [(p, n) for p, n in labels if p >= start and search in n.casefold()]
        result = {'plugin': name, 'total': count, 'start': start, 'next_start': None, 'params': []}
        limit = max(1, min(256, int(params.get('limit', 128))))
        for param, label in eligible:
            if file_mode and len(result['params']) >= limit:
                result['next_start'] = param
                break
            result['params'].append(read_param(where, param, params.get('display', True)))
            if not file_mode and len(json.dumps(result, separators=(',', ':'))) > 530:
                result['params'].pop()
                if not result['params']:
                    raise ValueError('Parameter label exceeds MIDI page budget; read by index')
                result['next_start'] = param
                break
        return result

    def get_param(params):
        return read_param(target(params), params['param'], params.get('display', True))

    def read_params(params):
        where, selectors = target(params), params['params']
        if not isinstance(selectors, list) or not 1 <= len(selectors) <= 128:
            raise ValueError('Read 1..128 explicit parameter indices or exact names')
        values = []
        for selector in selectors:
            value = resolve(where, selector)
            value['s'] = value_string(value['i'], where)
            values.append(value)
        return {'plugin': identity(where)[0], 'params': values, 'verification_scope': 'host_readback'}

    def set_param(params):
        where = target(params)
        param = resolve(where, params['param'])
        value = params['value']
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('Plugin value must be finite normalized 0..1')
        plugins.setParamValue(value, param['i'], where[0], where[1], 0, where[2])
        return read_param(where, param['i'])

    def find(params):
        where = target(params)
        _, labels = names(where)
        search = str(params['search']).casefold()
        matches = [{'i': p, 'name': n} for p, n in labels if search in n.casefold()]
        if file_mode:
            return {'total_matches': len(matches), 'matches': matches, 'next_start': None}
        offset = max(0, int(params.get('start', 0)))
        page = []
        result = {'total_matches': len(matches), 'matches': page, 'next_start': None}
        for index in range(offset, len(matches)):
            page.append(matches[index])
            if len(json.dumps(result, separators=(',', ':'))) > 530:
                page.pop()
                if not page:
                    raise ValueError('Parameter label exceeds page budget')
                result['next_start'] = index
                break
        return result

    def apply_params(params):
        where = target(params)
        changes = params['changes']
        if not isinstance(changes, list) or not 1 <= len(changes) <= 32:
            raise ValueError('Apply 1..32 distinct parameters in one request')
        if any(job['state'] in ('queued', 'checking', 'rollback') for job in jobs.values()):
            raise ValueError('Another parameter transaction is still active')
        if any(j['phase'] in ('start_queued', 'waiting', 'recording') for j in recording_jobs.values()):
            raise ValueError('Finish the recording job before a parameter transaction')
        prepared, seen = [], set()
        for change in changes:
            if not isinstance(change, dict) or set(change) - {'param', 'value', 'expect'} or not {'param', 'value'} <= set(change):
                raise ValueError('Parameter change requires param and value, optional expect')
            value = change['value']
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('Plugin value must be finite normalized 0..1')
            old = resolve(where, change['param'])
            if old['i'] in seen:
                raise ValueError('Duplicate parameter in one transaction')
            if 'expect' in change and abs(old['v'] - change['expect']) > .0001:
                raise ValueError('Parameter no longer matches the expected original value')
            seen.add(old['i'])
            prepared.append({'param': old['i'], 'name': old['name'], 'before': old['v'], 'requested': value,
                             'after': None, 'submitted': False, 'restored': None})
        token = '%x' % time.monotonic_ns()
        if len(jobs) >= 16:
            del jobs[next(iter(jobs))]
        jobs[token] = {'id': token, 'state': 'queued', 'where': where, 'identity': identity(where),
                       'changes': prepared, 'index': 0, 'rollback_index': -1, 'error': None, 'deadline': 0}
        if file_mode:
            tick()
            if jobs[token]['state'] in ('verified', 'restored', 'unknown'):
                return job_status({'id': token})
        return {'id': token, 'state': 'queued', 'count': len(prepared)}

    def job_status(params):
        job = jobs.get(params['id'])
        if job is None:
            raise ValueError('Transaction no longer exists in this controller session')
        result = {'id': job['id'], 'state': job['state'], 'index': job['index'],
                  'count': len(job['changes']), 'error': job['error'], 'changes': [], 'next_start': None,
                  'verification_scope': 'host_readback', 'persistence_verified': False}
        for index in range(max(0, int(params.get('start', 0))), len(job['changes'])):
            result['changes'].append({key: job['changes'][index][key] for key in
                                      ('param', 'name', 'before', 'requested', 'after', 'submitted', 'restored')})
            if not file_mode and len(json.dumps(result, separators=(',', ':'))) > 550:
                result['changes'].pop()
                if not result['changes']:
                    raise ValueError('Transaction detail exceeds MIDI page budget; use standalone file RPC')
                result['next_start'] = index
                break
        return result

    def cancel_job(params):
        job = jobs[params['id']]
        if job['state'] in ('queued', 'checking'):
            job['error'] = 'cancelled'
            job['state'] = 'rollback'
            job['rollback_index'] = min(job['index'], len(job['changes']) - 1)
        return job_status(params)

    def tick_once():
        now = time.monotonic()
        for job in list(jobs.values()):
            if job['state'] not in ('queued', 'checking', 'rollback'):
                continue
            try:
                where = job['where']
                if identity(where) != job['identity']:
                    job['state'], job['error'] = 'unknown', 'Plugin identity changed; no rollback was attempted'
                    continue
                if job['state'] == 'rollback':
                    index = job['rollback_index']
                    if index < 0:
                        job['state'] = 'restored' if all(c['restored'] is not False for c in job['changes']) else 'unknown'
                        continue
                    change = job['changes'][index]
                    current = read_param(where, change['param'], False)
                    if abs(current['v'] - change['before']) <= .0001:
                        change['restored'] = True
                    elif change.get('restoring'):
                        if now < change['restore_deadline']:
                            continue
                        change['restored'] = False
                    elif (current['name'] == change['name'] and change['submitted'] and
                          abs(current['v'] - (change['after'] if change['after'] is not None else change['requested'])) <= .0001):
                        plugins.setParamValue(change['before'], change['param'], where[0], where[1], 0, where[2])
                        change['restoring'], change['restore_deadline'] = True, now + 1.5
                        continue
                    else:
                        change['restored'] = False
                    job['rollback_index'] -= 1
                    continue
                if job['index'] == len(job['changes']):
                    job['state'] = 'verified'
                    continue
                change = job['changes'][job['index']]
                current = read_param(where, change['param'], False)
                if current['name'] != change['name']:
                    raise ValueError('Parameter identity changed')
                if job['state'] == 'queued':
                    if abs(current['v'] - change['before']) > .0001:
                        raise ValueError('Parameter changed since transaction snapshot')
                    plugins.setParamValue(change['requested'], change['param'], where[0], where[1], 0, where[2])
                    change['submitted'] = True
                    job['deadline'] = now + 1.5
                    job['state'] = 'checking'
                    current = read_param(where, change['param'], False)
                change['after'] = current['v']
                if abs(current['v'] - change['requested']) <= .0001:
                    job['index'] += 1
                    job['state'] = 'queued'
                elif now >= job['deadline']:
                    raise ValueError('Plugin did not confirm the requested value')
            except Exception as error:
                job['error'] = str(error)[:120]
                if job['state'] == 'rollback':
                    job['state'] = 'unknown'
                    continue
                job['state'] = 'rollback'
                job['rollback_index'] = min(job['index'], len(job['changes']) - 1)

    def tick():
        deadline = time.monotonic() + .004
        for _ in range(32):
            before = [(j['state'], j['index'], j['rollback_index'],
                       tuple(c.get('restoring', False) for c in j['changes'])) for j in jobs.values()]
            tick_once()
            after = [(j['state'], j['index'], j['rollback_index'],
                      tuple(c.get('restoring', False) for c in j['changes'])) for j in jobs.values()]
            if before == after or time.monotonic() >= deadline:
                break

    def recording_status(params):
        job = recording_jobs[params['id']]
        start = max(0, int(params.get('start', 0)))
        logs = job.get('observations', [])
        return {'id': job['id'], 'phase': job['phase'], 'pattern_number': job['pattern'],
                'applied': len(logs), 'scheduled': len(job.get('points', [])), 'error': job.get('error'),
                'observations': logs[start:start + 128], 'next_start': start + 128 if start + 128 < len(logs) else None,
                'clock': job.get('clock'), 'partial_events_may_remain': bool(logs) and job['phase'] != 'completed',
                'playing': bool(api_modules['transport'].isPlaying()), 'recording': bool(api_modules['transport'].isRecording())}

    def recording_prepare(params):
        identifier, pattern = params['id'], params['pattern_number']
        if identifier in recording_jobs: return recording_status({'id': identifier})
        if not owner_marker(): raise ValueError('Recording requires an explicitly owned session')
        if type(identifier) is not str or not identifier or type(pattern) is not int or not 1 <= pattern <= 999:
            raise ValueError('Choose an explicit job id and pattern 1..999')
        transport = api_modules['transport']
        if transport.isPlaying() or transport.isRecording(): raise ValueError('Stop and disarm before preparing a recording job')
        if any(j['phase'] in ('arm_queued', 'arming', 'armed', 'start_queued', 'waiting', 'recording') for j in recording_jobs.values()):
            raise ValueError('Another recording job is active')
        if any(j['state'] in ('queued', 'checking', 'rollback') for j in jobs.values()):
            raise ValueError('Finish the parameter transaction before recording')
        if len(recording_jobs) >= 16: del recording_jobs[next(iter(recording_jobs))]
        api_modules['patterns'].jumpToPattern(pattern)
        if api_modules['patterns'].patternNumber() != pattern: raise ValueError('FL did not select the recording pattern')
        recording_jobs[identifier] = {'id': identifier, 'pattern': pattern, 'owner': owner_marker(),
                                      'phase': 'arm_queued', 'observations': [], 'index': 0}
        return recording_status({'id': identifier})

    def recording_start(params):
        job = recording_jobs[params['id']]
        if job['phase'] != 'armed' or not api_modules['transport'].isRecording():
            raise ValueError('Complete the owned recording setup dialog before starting')
        if api_modules['transport'].isPlaying() or api_modules['patterns'].patternNumber() != job['pattern']:
            raise ValueError('Recording pattern or stopped transport changed')
        clock, points, stop = params['clock'], params['points'], params['stop_at']
        if clock not in ('seconds', 'ticks') or not isinstance(points, list) or not points:
            raise ValueError('Recording requires seconds/ticks and a nonempty points array')
        previous, prepared = -1, []
        for point in points:
            at, value, spec, event_id = point['at'], point['value'], point['target'], point['event_id']
            if (type(at) not in (int, float) or not math.isfinite(at) or at < 0 or at < previous or
                    (clock == 'ticks' and type(at) is not int) or type(value) not in (int, float) or not math.isfinite(value) or
                    type(event_id) is not int or not 0 <= event_id <= 0xffffffff):
                raise ValueError('Recording points require sorted times, finite values and explicit REC addresses')
            kind = spec['kind']
            if kind == 'tempo':
                if not 10 <= value <= 522 or event_id != 0x40000005: raise ValueError('Invalid tempo point')
            elif kind in ('channel_volume', 'channel_pan'):
                ch = spec['channel']
                if type(ch) is not int or not 0 <= ch < channels.channelCount(True): raise ValueError('Channel is absent')
                if not (-1 if kind == 'channel_pan' else 0) <= value <= 1: raise ValueError('Channel value is out of range')
            elif kind == 'mixer_volume':
                if type(spec['track']) is not int or not 0 <= spec['track'] <= mixer.getTrackCount() or not 0 <= value <= 1:
                    raise ValueError('Mixer target/value is out of range')
            elif kind in ('generator_param', 'effect_param'):
                where = target(spec)
                if not 0 <= value <= 1: raise ValueError('Plugin value must be normalized 0..1')
                read_param(where, spec['param'], False)
            else: raise ValueError('Unsupported recording target')
            midi_api = api_modules['midi']
            if kind == 'tempo': live_id = midi_api.REC_Tempo
            elif kind in ('channel_volume', 'channel_pan', 'generator_param'):
                offset = (midi_api.REC_Chan_Plugin_First + spec['param'] if kind == 'generator_param' else
                          midi_api.REC_Chan_Vol if kind == 'channel_volume' else midi_api.REC_Chan_Pan)
                live_id = channels.getRecEventId(spec['channel'], True) + offset
            else:
                live_id = mixer.getTrackPluginId(spec['track'], spec.get('slot', 0)) + (
                    midi_api.REC_Plug_Plugin_First + spec['param'] if kind == 'effect_param' else midi_api.REC_Mixer_Vol)
            live_id &= 0xffffffff
            if live_id == midi_api.REC_InvalidID or live_id != event_id:
                raise ValueError('Runtime REC address differs from the saved target; take a fresh native snapshot')
            prepared.append({'at': at, 'value': value, 'target': spec, 'event_id': event_id, 'live_event_id': live_id})
            previous = at
        if (type(stop) not in (int, float) or not math.isfinite(stop) or stop <= previous or
                (clock == 'ticks' and type(stop) is not int)):
            raise ValueError('stop_at must be later than the last point in the selected clock')
        job.update(clock=clock, points=prepared, stop_at=stop, phase='start_queued')
        return recording_status({'id': job['id']})

    def recording_finish(job, phase, error=None):
        job.update(phase=phase, error=error)
        if owner_marker() == job['owner']:
            transport = api_modules['transport']
            if transport.isPlaying(): transport.stop()
            if transport.isRecording(): transport.record()

    def recording_cancel(params):
        job = recording_jobs[params['id']]
        if job['phase'] in ('arm_queued', 'arming', 'armed', 'start_queued', 'waiting', 'recording'):
            recording_finish(job, 'cancelled')
        return recording_status({'id': job['id']})

    def recording_tick():
        for job in list(recording_jobs.values()):
            if job['phase'] not in ('arm_queued', 'arming', 'armed', 'start_queued', 'waiting', 'recording'): continue
            if job['phase'] == 'arming': continue
            try:
                transport = api_modules['transport']
                if owner_marker() != job['owner']: raise ValueError('Owned project changed')
                if api_modules['patterns'].patternNumber() != job['pattern']: raise ValueError('Selected recording pattern changed')
                if job['phase'] == 'arm_queued':
                    # The prepare reply is already written. A first-use modal
                    # may block this call; owned window observations still work.
                    job['phase'] = 'arming'
                    transport.record()
                    if not transport.isRecording(): raise ValueError('Recording setup was cancelled')
                    job['phase'] = 'armed'
                if job['phase'] == 'armed': continue
                if job['phase'] == 'start_queued':
                    if transport.getLoopMode() != 1: transport.setLoopMode()
                    job['start_tick'] = transport.getSongPos(2)
                    transport.start(); job['phase'] = 'waiting'
                now, position = time.perf_counter(), transport.getSongPos(2)
                if not transport.isPlaying() or not transport.isRecording(): raise ValueError('Transport or recording stopped before completion')
                if job['phase'] == 'waiting':
                    if position <= job['start_tick']: continue
                    job.update(phase='recording', origin=now, origin_tick=position, last_tick=position)
                if position < job['last_tick']: raise ValueError('Transport moved backwards during recording')
                job['last_tick'] = position
                elapsed = now - job['origin'] if job['clock'] == 'seconds' else position - job['origin_tick']
                budget = time.perf_counter() + .004
                while job['index'] < len(job['points']) and job['points'][job['index']]['at'] <= elapsed:
                    point = job['points'][job['index']]; spec, value = point['target'], point['value']; kind = spec['kind']
                    if kind == 'tempo': handlers['set_tempo']({'bpm': value}); observed = handlers['get_tempo']({})['bpm']
                    elif kind == 'channel_volume':
                        channels.setChannelVolume(spec['channel'], value, 0, True); observed = channels.getChannelVolume(spec['channel'], 0, True)
                    elif kind == 'channel_pan':
                        channels.setChannelPan(spec['channel'], value, 0, True); observed = channels.getChannelPan(spec['channel'], True)
                    elif kind == 'mixer_volume':
                        mixer.setTrackVolume(spec['track'], value); observed = mixer.getTrackVolume(spec['track'])
                    else:
                        where = target(spec); plugins.setParamValue(value, spec['param'], where[0], where[1], 0, where[2])
                        observed = plugins.getParamValue(spec['param'], *where)
                    signed_id = point['live_event_id'] if point['live_event_id'] <= 0x7fffffff else point['live_event_id'] - 0x100000000
                    raw = api_modules['general'].processRECEvent(signed_id, 0, api_modules['midi'].REC_GetValue)
                    if raw == api_modules['midi'].REC_InvalidID: raise ValueError('REC raw value is unavailable')
                    actual = time.perf_counter() - job['origin'] if job['clock'] == 'seconds' else transport.getSongPos(2) - job['origin_tick']
                    job['observations'].append({**point, 'actual': actual, 'lateness': actual - point['at'],
                        'position_tick': transport.getSongPos(2), 'observed_value': observed, 'raw_value': raw})
                    job['index'] += 1
                    if time.perf_counter() >= budget: break
                if elapsed >= job['stop_at'] and job['index'] == len(job['points']): recording_finish(job, 'completed')
            except Exception as error:
                recording_finish(job, 'failed', str(error))

    api_modules = {}
    if namespace is not None:
        rpc_directory = owned_directory
        rpc_prefix = os.environ.get('FLSTUDIO_CLI_SESSION_TOKEN', '')
        if editor_files:
            rpc_directory = namespace.get('_CLI_CONTROLLER_DIR') or os.path.dirname(os.path.abspath(namespace['__file__']))
            rpc_prefix = 'editor-' + instance + '-'
        file_heartbeat = [0.0]
        last_file_id = [None]
        for name in ('channels', 'mixer', 'patterns', 'playlist', 'transport', 'general', 'ui', 'arrangement',
                     'plugins', 'midi', 'device', 'utils', 'screen', 'launchMapPages'):
            try:
                api_modules[name] = __import__(name)
            except ImportError:
                pass

    def api_catalog(params):
        module = params.get('module')
        if module is None:
            return {'modules': sorted(api_modules)}
        if module not in api_modules:
            raise ValueError('Unknown FL API module')
        constants = params.get('kind') == 'constants'
        search = str(params.get('search', '')).casefold()
        methods = [n for n in dir(api_modules[module]) if not n.startswith('_') and search in n.casefold()
                   and (type(getattr(api_modules[module], n)) in (int, float, str, bool) if constants
                        else callable(getattr(api_modules[module], n)))]
        start, page = max(0, int(params.get('start', 0))), []
        result = {'module': module, 'total': len(methods), 'functions': page, 'next_start': None}
        for index in range(start, len(methods)):
            name = methods[index]
            page.append({'name': name, 'value': getattr(api_modules[module], name)} if constants else name)
            if not file_mode and len(json.dumps(result)) > 530:
                page.pop(); result['next_start'] = index; break
        return result

    def api_call(params):
        module, name = params['module'], params['function']
        if module not in api_modules or not isinstance(name, str) or name.startswith('_'):
            raise ValueError('Choose a public function from a supported FL API module')
        function = getattr(api_modules[module], name, None)
        if not callable(function):
            raise ValueError('FL API function is unavailable')
        args, kwargs = params.get('args', []), params.get('kwargs', {})
        if not isinstance(args, list) or not isinstance(kwargs, dict):
            raise ValueError('API args must be an array and kwargs an object')
        value = function(*args, **kwargs)
        if isinstance(value, float) and not math.isfinite(value):
            return {'value': None, 'nonfinite_value': 'nan' if math.isnan(value) else
                    'negative_infinity' if value < 0 else 'positive_infinity'}
        data = {'value': value}
        return data

    def api_batch(params):
        calls = params['calls']
        if not isinstance(calls, list) or not 1 <= len(calls) <= 128:
            raise ValueError('API batch requires 1..128 calls')
        # Resolve every function and argument shape before the first call.
        for call in calls:
            if (not isinstance(call, dict) or call.get('module') not in api_modules or
                not isinstance(call.get('function'), str) or call['function'].startswith('_') or
                not callable(getattr(api_modules[call['module']], call['function'], None)) or
                not isinstance(call.get('args', []), list) or not isinstance(call.get('kwargs', {}), dict)):
                raise ValueError('Batch requires public functions with array args and object kwargs')
        results = []
        for call in calls:
            try: results.append({'ok': True, **api_call(call)})
            except Exception as error:
                results.append({'ok': False, 'error': str(error)[:240]}); break
        return {'results': results, 'complete': len(results) == len(calls) and all(r['ok'] for r in results)}

    def save_project(params):
        if owner_marker() is None:
            raise ValueError('Automatic saving requires an explicitly owned session')
        api_modules['transport'].globalTransport(api_modules['midi'].FPT_Save, 1)
        return {'requested': True}

    handlers.update({'cli_capabilities': lambda p: {'revision': REVISION, 'global_generator_params': True,
                      'plugin_transactions': True, 'recording_jobs': True, 'api_catalog': bool(api_modules), 'instance': instance},
                     'cli_plugin_info': info, 'cli_plugin_params': get_params, 'cli_plugin_find': find,
                     'cli_plugin_read': read_params,
                     'cli_plugin_get_param': get_param, 'cli_plugin_set_param': set_param,
                     'cli_plugin_apply': apply_params, 'cli_plugin_job': job_status, 'cli_plugin_cancel': cancel_job,
                     'cli_api_catalog': api_catalog, 'cli_api_call': api_call, 'cli_api_batch': api_batch,
                     'cli_record_prepare': recording_prepare, 'cli_record_start': recording_start,
                     'cli_record_status': recording_status, 'cli_record_cancel': recording_cancel,
                     'cli_project_save': save_project,
                     'cli_session_info': lambda p: {'instance': instance, 'owner_marker': owner_marker(),
                        'channel_count': channels.channelCount(True), 'active_plugin_jobs':
                        [j['id'] for j in jobs.values() if j['state'] in ('queued', 'checking', 'rollback')],
                        'active_recording_jobs': [j['id'] for j in recording_jobs.values() if j['phase'] in
                            ('arm_queued', 'arming', 'armed', 'start_queued', 'waiting', 'recording')]},
                     'cli_channel_plugin_params': get_params, 'cli_channel_plugin_get_param': get_param,
                     'cli_channel_plugin_set_param': set_param})

    if namespace is not None:
        incoming, requests = {}, []
        observed_owner, ever_owned = [None], [False]
        last_heartbeat = [0.0]
        original_heartbeat = namespace.get('_emit_heartbeat')
        def legacy_heartbeat():
            if original_heartbeat and not render_mode and rpc_directory is None and owner_marker() is None:
                original_heartbeat()
        namespace['_emit_heartbeat'] = legacy_heartbeat
        def send(direction, identifier, data):
            fn = namespace.get('_send_sysex_fn')
            if fn:
                encoded = base64.b64encode(json.dumps(data, separators=(',', ':'), ensure_ascii=True).encode('utf-8'))
                header = PREFIX + bytes([direction]) + identifier.encode('ascii')
                if len(encoded) <= 720:
                    fn(b'\xf0' + header + encoded + b'\xf7')
                else:
                    count = (len(encoded) + 719) // 720
                    if count > 127:
                        raise ValueError('API result exceeds 68 KiB; select a smaller range')
                    for index in range(count):
                        body = PREFIX + b'\x05' + identifier.encode('ascii') + bytes([index, count]) + encoded[index * 720:(index + 1) * 720]
                        fn(b'\xf0' + body + b'\xf7')
        def wrap_event(original):
            def on_event(event):
                raw = bytes(getattr(event, 'sysex', b'') or b'')
                if raw[:1] == b'\xf0': raw = raw[1:]
                if raw[-1:] == b'\xf7': raw = raw[:-1]
                if raw[:4] in (PREFIX, b'\x7dMCP'):
                    if getattr(event, 'handled', False): return
                    event.handled = True
                    if rpc_directory is not None or render_mode: return
                    legacy = raw[:4] != PREFIX
                    if legacy and ever_owned[0]: return
                    if len(raw) < 13 or raw[4] not in (1, 4): return
                    identifier = raw[5:13].decode('ascii')
                    encoded = raw[13:]
                    if raw[4] == 4:
                        if legacy: return
                        if len(raw) < 15: return
                        part, count = raw[13], raw[14]
                        if not 0 <= part < count <= 127: return
                        if part == 0:
                            incoming.clear()
                            incoming[identifier] = [count, {}]
                        assembly = incoming.get(identifier)
                        if assembly is None or assembly[0] != count: return
                        assembly[1][part] = raw[15:]
                        if len(assembly[1]) != count: return
                        encoded = b''.join(assembly[1][i] for i in range(count))
                        del incoming[identifier]
                    request = json.loads(base64.b64decode(encoded).decode('utf-8'))
                    if not legacy and request.get('instance') != instance: return
                    marker = request.get('owner_marker')
                    if marker is not None and marker != observed_owner[0]: return
                    # MIDI callbacks may hold FL's MIDI/audio locks. Calling
                    # plugins here can deadlock the UI against that thread.
                    # Decode only; all host APIs run from the UI's OnIdle.
                    requests.append((legacy, identifier, request))
                    return
                if original is not None: original(event)
            return on_event
        namespace['OnSysEx'] = wrap_event(namespace.get('OnSysEx'))
        namespace['OnMidiMsg'] = wrap_event(namespace.get('OnMidiMsg'))
        original_idle = namespace.get('OnIdle')
        def invoke(request):
            try:
                if request.get('instance', instance) != instance:
                    raise ValueError('Controller instance changed')
                if request.get('owner_marker') is not None and request['owner_marker'] != observed_owner[0]:
                    raise ValueError('Owned project changed before command execution')
                if time.time() > request.get('expires_at', float('inf')):
                    raise ValueError('Request expired before execution; no changes applied')
                data = handlers[request['cmd']](request.get('params') or {})
                # Reject unsupported host results inside the request envelope,
                # before a serialization error can interrupt OnIdle/heartbeat.
                json.dumps(data, allow_nan=False)
                return {'v': 2, 'ok': True, 'data': data, 'instance': instance, 'id': request.get('id')}
            except Exception as error:
                return {'v': 2, 'ok': False, 'error': str(error)[:240], 'instance': instance, 'id': request.get('id')}

        def write_reply(path, value):
            # MIDI-script sandbox permits open/read/write, but not directory
            # enumeration, rename or deletion. The host serializes requests.
            encoded = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
            with open(path, 'w', encoding='utf-8') as file:
                file.write(encoded)

        def service_files():
            if rpc_directory is None: return
            try:
                with open(os.path.join(rpc_directory, rpc_prefix + 'request.json'), 'r', encoding='utf-8') as file:
                    request = json.load(file)
            except (FileNotFoundError, ValueError):
                request = None
            if request and request.get('id') != last_file_id[0]:
                last_file_id[0] = request.get('id')
                write_reply(os.path.join(rpc_directory, rpc_prefix + 'response.json'), invoke(request))
            if time.monotonic() - file_heartbeat[0] >= .5:
                file_heartbeat[0] = time.monotonic()
                write_reply(os.path.join(rpc_directory, rpc_prefix + 'state.json'),
                            {'instance': instance, 'owner_marker': observed_owner[0], 'revision': REVISION,
                             'pid': os.getpid(), 'ts': time.time()})

        def idle():
            if render_mode: return
            observed_owner[0] = owner_marker()
            if observed_owner[0] is not None:
                ever_owned[0] = True
            if rpc_directory is None and original_idle: original_idle()
            for legacy, identifier, request in requests[:8]:
                del requests[0]
                reply = invoke(request)
                if legacy:
                    namespace['_send_message'](2, identifier, reply)
                else:
                    send(2, identifier, reply)
            service_files()
            recording_tick()
            tick()
            now = time.monotonic()
            if rpc_directory is None and now - last_heartbeat[0] >= .5:
                last_heartbeat[0] = now
                send(3, '00000000', {'v': 2, 'instance': instance, 'owner_marker': owner_marker(), 'revision': REVISION})
        namespace['OnIdle'] = idle
    print('[FL Studio CLI] extension ready: ' + REVISION)
