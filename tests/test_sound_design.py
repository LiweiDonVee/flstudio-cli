"""State/signal invariants; real FL acceptance is recorded separately."""
from pathlib import Path
import array
import math
import wave

import pytest

from flstudio_cli.flp import Project, create_project
from flstudio_cli.sound_state import state_view, transfer, channel_events
from flstudio_cli.sound_design import prepare, candidate, apply_candidate, write

INSTALL=Path('C:/Program Files/Image-Line/FL Studio 2026')


def context(tmp_path):
    preset=INSTALL/'Data/Patches/Plugin presets/Generators/Sytrus/Default.fst'
    notes=[{'key':36,'start_tick':0,'length_tick':72,'velocity':90}]
    project=create_project({'tempo_bpm':120,'channels':[
        {'name':'Target','plugin_preset':str(preset),'mixer_track':1},
        {'name':'Preserved','plugin_preset':str(preset),'mixer_track':2}],
        'patterns':[{'number':1,'scores':[{'channel_index':i,'notes':notes} for i in range(2)]}],
        'playlist':[{'pattern_number':1,'track':1,'start_tick':0,'length_tick':192}]},
        INSTALL/'Data/Templates/Minimal/Basic/Basic.flp')
    return project.save(tmp_path/'source.flp')


def test_complete_sound_transfer_and_preconditions(tmp_path):
    from flstudio_cli.sytrus import set_parameters
    source=context(tmp_path)
    before=Project.read(source)
    donor=Project.read(source)
    set_parameters(donor,0,[{'param':'op2.volume','value_raw':100}])
    # Opaque bytes are transferred as well as host overrides.
    state=next(e for e in channel_events(donor,0) if e.id==213)
    state.data += b'opaque-test-trailer'
    # FX slot-0 controls share a group with the track send. Undo must compare
    # and transfer only slot controls, while preserving that unrelated send.
    from flstudio_cli.mixing import apply_chains
    apply_chains(donor,[{'track':1,'slots':[{'slot':0,'preset':str(INSTALL/'Data/Patches/Plugin presets/Effects/Fruity Reeverb 2/Default.fst'),'wet':.12}]}])
    other=[(e.id,e.data) for e in channel_events(before,1)]
    transfer(before,0,donor,0)
    assert state_view(before,0)==state_view(donor,0)
    assert [(e.id,e.data) for e in channel_events(before,1)]==other
    assert before.patterns()==Project.read(source).patterns()
    transfer(before,0,Project.read(source),0)
    assert state_view(before,0)==state_view(Project.read(source),0)
    before.set_channel(1,{'mixer_track':1})
    with pytest.raises(ValueError,match='shared'):
        transfer(before,0,donor,0)
    # The receiving project may reorder identical-sounding channel instances.
    # Resolve the original IID rather than trusting the old numeric index.
    task=prepare(source,0,tmp_path/'task','preserve identity','bass')
    folder=tmp_path/'task/candidates/choice'; folder.mkdir()
    donor.save(folder/'sound.flp')
    write(folder/'candidate.json',{'phase':'ready','artifact':str(folder/'sound.flp')})
    reordered=Project.read(source); spans=reordered.channel_spans()
    a,b=spans[0]; c,d=spans[1]
    reordered.events[a:d]=reordered.events[c:d]+reordered.events[b:c]+reordered.events[a:b]
    reordered.save(tmp_path/'reordered.flp')
    apply_candidate(Path(task['task_file']),'choice',tmp_path/'reordered.flp',tmp_path/'applied.flp')
    applied=Project.read(tmp_path/'applied.flp')
    assert applied.channels()[1]['iid']==task['target']['iid']
    assert state_view(applied,1)==state_view(donor,0)
    assert state_view(applied,0)==state_view(Project.read(source),1)


def test_invalid_values_fail_before_starting_a_worker(tmp_path):
    source=context(tmp_path)
    task=prepare(source,0,tmp_path/'task','bass remains clear','bass')
    request={'id':'bad','description':'Invalid physical-unit request','mechanisms':['envelope'],
             'params':[{'param':3,'value':250}]}
    with pytest.raises(ValueError,match='normalized'):
        candidate(Path(task['task_file']),request)
    assert not (tmp_path/'task/candidates/bad').exists()
    assert source.read_bytes()==(tmp_path/'task/original.flp').read_bytes()


def test_preview_matching_preserves_raw_and_dynamics(tmp_path):
    pytest.importorskip('numpy')
    from flstudio_cli.sound_audio import analyze,load,matched_previews,compare
    paths=[]
    for i,gain in enumerate((.1,.5)):
        path=tmp_path/f'{i}.wav'
        signal=array.array('h',(round(32767*gain*math.sin(2*math.pi*440*n/44100)) for n in range(44100)))
        with wave.open(str(path),'wb') as f:
            f.setparams((1,2,44100,0,'NONE','')); f.writeframes(signal.tobytes())
        paths.append(path)
    original=[p.read_bytes() for p in paths]
    result=matched_previews(paths,tmp_path/'preview')
    levels=[analyze(Path(row['preview']))['rms_dbfs'] for row in result['files']]
    assert max(levels)-min(levels)<.005
    assert [p.read_bytes() for p in paths]==original
    assert all(analyze(Path(row['preview']))['sample_peak_count']==0 for row in result['files'])
    assert compare(paths[0],paths[0])['pcm_equal']


def test_named_articulation_preserves_other_note_bits():
    from flstudio_cli.note_values import validate,articulation
    original={'key':36,'start_tick':0,'length_tick':96,'velocity':90,'flags':0x4400,'midi_channel':0x80}
    marked=validate({**original,'slide':True,'porta':True,'muted':True,'color':5})
    assert marked['flags']==0x4408 and marked['midi_channel']==0xb5
    assert articulation(marked)=={'slide':True,'porta':True,'muted':True,'color':5}
    cleared=validate({**marked,'slide':False,'porta':False,'muted':False,'color':0})
    assert cleared['flags']==original['flags'] and cleared['midi_channel']==original['midi_channel']


def test_signal_diagnostics_separate_gain_timbre_and_unknown_pitch(tmp_path):
    np=pytest.importorskip('numpy')
    from flstudio_cli.audio_analysis import analyze
    t=np.arange(44100)/44100
    paths=[]
    for i,s in enumerate((.1*np.sin(2*np.pi*110*t),.3*np.sin(2*np.pi*110*t),
                          .1*np.sin(2*np.pi*110*t)+.03*np.sin(2*np.pi*330*t),np.zeros_like(t))):
        p=tmp_path/f'signal-{i}.wav'
        with wave.open(str(p),'wb') as f:
            f.setparams((1,2,44100,0,'NONE',''));f.writeframes(np.round(s*32767).astype('<i2').tobytes())
        paths.append(p)
    gain=analyze(paths[1],'harmonics',{'fundamental_hz':110},paths[0])
    color=analyze(paths[2],'harmonics',{'fundamental_hz':110},paths[0])
    assert gain['observations']['gain_fit'][0]['constant_gain_within_minus60db']
    assert not color['observations']['gain_fit'][0]['constant_gain_within_minus60db']
    assert analyze(paths[0],'pitch')['reason_code']=='monophonic_context_not_confirmed'
    assert analyze(paths[3],'pitch',{'monophonic':True})['usability']=='unavailable'
