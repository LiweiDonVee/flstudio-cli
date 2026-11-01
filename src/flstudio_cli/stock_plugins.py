"""Small native Producer-plugin designs, sharing saved target selection only."""
import struct

from .native_curves import number
from .plugin_state import events

WAVES=('sine','triangle','square','saw','rounded_saw','noise','sample')
DELAY_FIELDS=('input_wet','model','tempo_sync','keep_pitch','time','offset','smoothing','stereo_spread',
              'mod_rate','mod_time','mod_cutoff','smear','cross','limit_mode','feedback','filter_type',
              'filter_cutoff','filter_resonance','distortion_level','distortion_knee','distortion_symmetry',
              'sample_rate','bit_depth','output_wet','output_tone','output_dry')
OSC_VOLUME={'enabled':168,'predelay_raw':172,'attack_raw':176,'hold_raw':180,'decay_raw':184,
            'sustain_raw':188,'release_raw':192,'amount_raw':196}


def _osc_layout(data):
    if len(data)==44 and 0<=struct.unpack_from('<i',data)[0]<7:
        return 'factory-v0',[{'waveform':0,'coarse_semitones':4,'fine_cents':8},
                            {'waveform':16,'coarse_semitones':20,'fine_cents':24},
                            {'waveform':32,'coarse_semitones':36,'fine_cents':40}],{'mix2_raw':12,'mix3_raw':28}
    if len(data)==460 and struct.unpack_from('<i',data)[0]==14:
        return 'fl26-v14',[dict(zip(('pan_raw','waveform','coarse_semitones','fine_cents','phase_raw','detune_cents'),range(4+i*28,28+i*28,4)))
                           for i in range(3)],{'mix2_raw':28,'mix3_raw':56,'phase_random_raw':84}
    raise ValueError('Unsupported 3x Osc state; use the installed Default family and a native FL26 save')


def inspect(project,target):
    name,block=events(project,target);data=block[213].data
    if name=='3x Osc':
        profile,rows,globals_=_osc_layout(data);osc=[]
        for i,fields in enumerate(rows):
            row={k:struct.unpack_from('<i',data,at)[0] for k,at in fields.items()}
            if not 0<=row['waveform']<len(WAVES):raise ValueError('Unsupported oscillator waveform')
            row.update(oscillator=i+1,waveform=WAVES[row['waveform']]);osc.append(row)
        return {'plugin':name,'profile':profile,'oscillators':osc,
                **{k:struct.unpack_from('<i',data,at)[0] for k,at in globals_.items()},
                **({'volume_envelope':{k:(bool(struct.unpack_from('<i',data,at)[0]) if k=='enabled' else struct.unpack_from('<i',data,at)[0]) for k,at in OSC_VOLUME.items()}} if profile=='fl26-v14' else {}),
                'limitations':['Sample waveform requires its separate sample resource. Factory v0 lacks per-oscillator pan/phase/detune fields.',
                               'mix2_raw/mix3_raw are FL mixer controls, not independent linear oscillator gains. Channel/host envelopes are separate.']}
    if name=='Fruity Delay 3':
        if len(data)!=108 or struct.unpack_from('<i',data)[0]!=1:raise ValueError('Unsupported Delay 3 native state')
        values=dict(zip(DELAY_FIELDS,struct.unpack_from('<26i',data,4)))
        return {'plugin':name,'controls_raw':values,'time_steps':values['time']/48 if values['tempo_sync'] else None,
                'limitations':['Raw native controls are not presumed to be Hz, milliseconds or percent. Synced time is steps (one step is a sixteenth note).']}
    if name in ('Maximus','Fruity WaveShaper'):
        from .native_curves import describe
        return describe(name,data)
    if name in ('Edison','Slicex'):
        from .sample_editors import describe
        return describe(name,data)
    raise ValueError(f'No scoped native design adapter for {name!r}; use host controls or native UI/capture')


def edit(project,target,request):
    name,block=events(project,target);data=block[213].data
    # Validate and operate on local bytes. Publication to the Project is last.
    before=inspect(project,target)
    if name=='3x Osc':
        profile,rows,globals_=_osc_layout(data);raw=bytearray(data)
        if not isinstance(request,dict) or not request or set(request)-{'oscillators','volume_envelope',*globals_}:raise ValueError('Unknown 3x Osc design field')
        seen=set()
        for row in request.get('oscillators',[]):
            if not isinstance(row,dict) or 'oscillator' not in row or type(row['oscillator']) is not int or not 1<=row['oscillator']<=3:raise ValueError('Choose oscillator 1..3')
            index=row['oscillator']-1
            if index in seen:raise ValueError('Duplicate oscillator')
            seen.add(index);fields=rows[index]
            if set(row)-{'oscillator',*fields}:raise ValueError('Unknown or unavailable oscillator field; native-save a legacy preset to expose pan/phase/detune')
            for key,value in row.items():
                if key=='oscillator':continue
                if key=='waveform':
                    if value not in WAVES:raise ValueError('Choose a named 3x Osc waveform')
                    if value=='sample':raise ValueError('Sample-waveform design requires a separately verified sample binding; use Sampler/Slicex')
                    value=WAVES.index(value)
                else:
                    lo,hi={'coarse_semitones':(-24,24),'fine_cents':(-100,100),'pan_raw':(-64,64),'phase_raw':(-64,64),'detune_cents':(-100,100)}[key]
                    if type(value) is not int or not lo<=value<=hi:raise ValueError(f'{key} must be integer {lo}..{hi}')
                struct.pack_into('<i',raw,fields[key],value)
        for key,at in globals_.items():
            if key in request:
                value=request[key]
                if type(value) is not int or not 0<=value<=128:raise ValueError(f'{key} must be integer 0..128')
                struct.pack_into('<i',raw,at,value)
        if 'volume_envelope' in request:
            if profile!='fl26-v14':raise ValueError('Native-save the 3x Osc Default family before editing its volume envelope')
            envelope=request['volume_envelope']
            if not isinstance(envelope,dict) or not envelope or set(envelope)-set(OSC_VOLUME):raise ValueError('Unknown 3x Osc volume envelope field')
            for key,value in envelope.items():
                if key=='enabled':
                    if type(value) is not bool:raise ValueError('Envelope enabled must be boolean')
                    value=int(value)
                else:
                    lo,hi=(0,128) if key=='sustain_raw' else (-128,128) if key=='amount_raw' else (100,65536)
                    if type(value) is not int or not lo<=value<=hi:raise ValueError(f'{key} must be integer {lo}..{hi}; times are native units, not milliseconds')
                struct.pack_into('<i',raw,OSC_VOLUME[key],value)
        data=bytes(raw)
    elif name=='Fruity Delay 3':
        if not isinstance(request,dict) or not request or set(request)-{'controls_raw','time_steps'}:raise ValueError('Delay 3 accepts controls_raw and synced time_steps')
        changes=request.get('controls_raw',{})
        if not isinstance(changes,dict) or set(changes)-set(DELAY_FIELDS):raise ValueError('Unknown Delay 3 control')
        raw=bytearray(data)
        bounds={'model':(0,3),'tempo_sync':(0,1),'keep_pitch':(0,1),'limit_mode':(0,2),'filter_type':(0,2),'offset':(-6000,6000),'output_tone':(-6000,6000),'time':(0,768),'sample_rate':(0,60000)}
        for key,value in changes.items():
            lo,hi=bounds.get(key,(0,6000))
            if type(value) is not int or not lo<=value<=hi:raise ValueError(f'{key} native value must be integer {lo}..{hi}')
            struct.pack_into('<i',raw,4+DELAY_FIELDS.index(key)*4,value)
        if 'time_steps' in request:
            steps=number(request['time_steps'],1/48,16,'Delay time steps');native=steps*48
            if abs(native-round(native))>1e-6:raise ValueError('Synced delay resolves to 1/48th of a step')
            struct.pack_into('<i',raw,4+2*4,1);struct.pack_into('<i',raw,4+4*4,round(native))
        data=bytes(raw)
    elif name in ('Maximus','Fruity WaveShaper'):
        from .native_curves import edit as edit_curve
        data=edit_curve(name,data,request)
    elif name in ('Edison','Slicex'):
        from .sample_editors import edit as edit_sample
        data=edit_sample(name,data,request)
    else:raise ValueError('No native design adapter for this plugin')
    old=block[213].data
    try:
        block[213].data=data;after=inspect(project,target)
    except Exception:
        block[213].data=old;raise
    project._channel_cache=None
    return {'target':target,'plugin':name,'before':before,'after':after,'live_applied':False,'readback_scope':'saved_native_state'}


def register(app,emit,json_option):
    from pathlib import Path
    import click
    from .flp import Project
    from .contracts import Result
    from .json_output import decode_json
    group=app.commands['plugin']
    def target_options(fn):
        for args,kwargs in [ (('--project',),{'required':True,'type':click.Path(path_type=Path)}),
                             (('--channel',),{'type':click.IntRange(0)}),
                             (('--track',),{'type':click.IntRange(0)}),
                             (('--slot',),{'type':click.IntRange(0,9)}) ]:
            fn=click.option(*args,**kwargs)(fn)
        return fn
    def target(channel,track,slot):
        if channel is not None and track is None and slot is None:return {'channel':channel}
        if channel is None and track is not None and slot is not None:return {'track':track,'slot':slot}
        raise ValueError('Choose --channel or --track plus --slot')
    @group.command('design-inspect')
    @target_options
    @json_option
    def observe(project,channel,track,slot):
        data=inspect(Project.read(project),target(channel,track,slot))
        emit(Result(command='plugin design-inspect',status='verified',verified_scopes=['saved_native_design_fields'],data=data))
    @group.command('design-edit')
    @target_options
    @click.option('--request',required=True,type=click.Path(path_type=Path))
    @click.option('--output',required=True,type=click.Path(path_type=Path))
    @click.option('--dry-run',is_flag=True)
    @json_option
    def change(project,channel,track,slot,request,output,dry_run):
        if output.exists() or not output.parent.is_dir():raise ValueError('Choose a new FLP output in an existing directory')
        doc=Project.read(project);selected=target(channel,track,slot)
        result=edit(doc,selected,decode_json(request.read_text(encoding='utf-8-sig')))
        if not dry_run:
            doc.save(output)
            if inspect(Project.read(output),selected)!=result['after']:raise ValueError('Native design file readback differs')
        emit(Result(command='plugin design-edit',status='planned' if dry_run else 'artifact_ready',
                    verified_scopes=[] if dry_run else ['saved_native_design_fields'],
                    data={**result,'output':str(output.resolve()),'file_effects':[] if dry_run else [str(output.resolve())],
                          'native_fl_verification':'Run sound-design candidate and audition to prove native save/reopen/audio'}))
    @group.command('sample-export')
    @target_options
    @click.option('--deck',default='a',type=click.Choice(['a','b']))
    @click.option('--output',required=True,type=click.Path(path_type=Path))
    @json_option
    def export_sample(project,channel,track,slot,deck,output):
        from .sample_editors import export
        name,block=events(Project.read(project),target(channel,track,slot))
        data=export(name,block[213].data,output,deck)
        emit(Result(command='plugin sample-export',status='artifact_ready',verified_scopes=['embedded_native_audio'],data=data))
