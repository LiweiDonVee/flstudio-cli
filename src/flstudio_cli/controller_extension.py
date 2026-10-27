"""FL MIDI-script extension, installed as flstudio_cli_extension.py beside a controller.

This module runs inside FL's Python environment, with no CLI dependencies.
"""
import json


REVISION = 'flstudio-cli-sytrus-1'


def install(handlers):
    import channels
    import plugins

    def target(params):
        channel = params.get('channel')
        if type(channel) is not int or not 0 <= channel < channels.channelCount(True):
            raise ValueError('Choose an existing global channel index')
        if not plugins.isValid(channel, -1, True):
            raise ValueError('No generator plugin at global channel %d' % channel)
        return channel

    def plugin_name(channel):
        return plugins.getPluginName(channel, -1, False, True)

    def parameter(channel, index):
        count = plugins.getParamCount(channel, -1, True)
        if type(index) is not int or not 0 <= index < count:
            raise ValueError('Generator parameter index is out of range')
        return {'i': index, 'name': plugins.getParamName(index, channel, -1, True),
                'v': round(plugins.getParamValue(index, channel, -1, True), 4),
                's': plugins.getParamValueString(index, channel, -1, True) or ''}

    def get_params(params):
        channel = target(params)
        total = plugins.getParamCount(channel, -1, True)
        start = max(0, int(params.get('start', 0)))
        search = str(params.get('search', '')).casefold()
        index, out, scanned = start, [], 0
        result = {'channel': channel, 'index_scope': 'global', 'plugin': plugin_name(channel),
                  'total': total, 'start': start, 'next_start': None, 'params': out}
        while index < total and scanned < 150:
            name = plugins.getParamName(index, channel, -1, True)
            scanned += 1
            if name and search in name.casefold():
                out.append(parameter(channel, index))
                if len(json.dumps(result, separators=(',', ':'))) > 525:
                    out.pop()
                    if not out:
                        raise ValueError('Generator label exceeds transport budget; query the parameter by index')
                    break
            index += 1
        result['next_start'] = index if index < total else None
        return result

    def get_param(params):
        channel = target(params)
        return dict(parameter(channel, params['param']), channel=channel,
                    plugin=plugin_name(channel), index_scope='global')

    def set_param(params):
        channel = target(params)
        index, value = params['param'], params['value']
        parameter(channel, index)
        if type(value) not in (float, int) or not 0 <= value <= 1:
            raise ValueError('Live generator value must be normalized 0..1')
        plugins.setParamValue(value, index, channel, -1, 0, True)
        return get_param(params)

    handlers.update({'cli_capabilities': lambda p: {'revision': REVISION, 'global_generator_params': True},
                     'cli_channel_plugin_params': get_params, 'cli_channel_plugin_get_param': get_param,
                     'cli_channel_plugin_set_param': set_param})
    print('[FL Studio CLI] generator extension ready: ' + REVISION)
