"""Question-led signal observations for agents that cannot listen.

No taste score, pitch imputation or audio model. All temporal measurements state
their window resolution; periodicity is not a probability or proof of one voice.
"""
from collections import Counter
from pathlib import Path
import math

from .sound_audio import _numpy,load,_db,_spectrum,BANDS


def pitch_trace(signal,rate,*,fmin=40.,fmax=2000.,window_ms=100.,hop_ms=10.,min_confidence=.90,
                floor_dbfs=-80.,max_points=32,detail=False):
    np=_numpy();x=np.asarray(signal,dtype=np.float64)
    if x.ndim==1:x=x[:,None]
    if x.ndim!=2 or not np.isfinite(x).all():raise ValueError('Expected finite PCM frames x channels')
    if not 0<fmin<fmax<rate/2:raise ValueError('Invalid pitch search bounds')
    if not 0<min_confidence<=1 or type(max_points) is not int or not 1<=max_points<=32:raise ValueError('Invalid confidence or summary limit')
    if not 10<=window_ms<=2000 or not 1<=hop_ms<=1000:raise ValueError('Invalid analysis window/hop')
    n=round(rate*window_ms/1000);hop=max(1,round(rate*hop_ms/1000));lo=max(1,math.ceil(rate/fmax));hi=math.floor(rate/fmin)
    if n<3*hi or hi+1>=n:raise ValueError('Pitch window must cover at least three periods at min_hz; enlarge window_ms for lower notes')
    size=1<<(2*n-1).bit_length();lags=np.arange(hi+1);floor=10**(floor_dbfs/20);channels=[]
    for ch in range(x.shape[1]):
        rows=[]
        for start in range(0,len(x)-n+1,hop):
            s=x[start:start+n,ch];s=s-s.mean();rms=float(np.sqrt(np.mean(s*s)))
            row={'seconds':(start+(n-1)/2)/rate,'hz':None,'periodicity':None,'confidence':0.,'reason':None}
            if rms<floor:row['reason']='below_level_floor';rows.append(row);continue
            z=np.fft.rfft(s,size);ac=np.fft.irfft(z*z.conj(),size)[:hi+1];energy=np.concatenate(([0.],np.cumsum(s*s)))
            denominator=energy[n-lags]+energy[n]-energy[lags]
            nsdf=np.divide(2*ac,denominator,out=np.zeros_like(ac),where=denominator>1e-20)
            peaks=np.flatnonzero((nsdf[1:-1]>nsdf[:-2])&(nsdf[1:-1]>=nsdf[2:]))+1;peaks=peaks[(peaks>=lo)&(peaks<hi)]
            if not len(peaks):row['reason']='no_periodic_peak_in_range';rows.append(row);continue
            best=float(nsdf[peaks].max());admitted=peaks[nsdf[peaks]>=max(min_confidence,.90*best)]
            if not len(admitted):
                row.update(periodicity=best,confidence=max(0.,min(1.,best)),reason='low_periodicity');rows.append(row);continue
            lag=int(admitted[0]);score=float(nsdf[lag]);alternatives=[]
            for other in peaks:
                if other==lag:continue
                other_score=float(nsdf[other]);ratio=float(other)/lag;multiple=round(ratio);inverse=round(1/ratio)
                lower=multiple in (2,3,4) and abs(ratio-multiple)<=.03*multiple and other_score>score+.01
                upper=inverse in (2,3,4) and abs(1/ratio-inverse)<=.03*inverse and other_score>=max(min_confidence-.05,score-.04)
                if lower or upper:alternatives.append({'hz':rate/float(other),'periodicity':other_score})
            row.update(periodicity=score,confidence=max(0.,min(1.,score)))
            if alternatives:row.update(reason='harmonic_period_ambiguity',alternatives=alternatives[:4])
            else:
                a,b,c=nsdf[lag-1:lag+2];den=a-2*b+c
                correction=float(np.clip(.5*(a-c)/den,-.5,.5)) if abs(den)>1e-12 else 0.
                hz=rate/(lag+correction)
                if fmin<=hz<=fmax:row['hz']=float(hz)
                else:row['reason']='estimate_at_search_boundary'
            rows.append(row)
        indices=np.unique(np.linspace(0,len(rows)-1,min(max_points,len(rows))).round().astype(int)) if rows else []
        valid=[r for r in rows if r['hz'] is not None];active=sum(r['reason']!='below_level_floor' for r in rows)
        item={'channel':ch,'frame_count':len(rows),'tracked_frame_count':len(valid),'tracked_active_fraction':len(valid)/active if active else 0.,
              'null_reasons':dict(Counter(r['reason'] for r in rows if r['reason'])),'summary':[rows[i] for i in indices]}
        if valid:item['tracked_range_hz']=[min(r['hz'] for r in valid),max(r['hz'] for r in valid)]
        if detail:item['frames']=rows
        channels.append(item)
    return {'method':'FFT normalized square difference, first strong peak, parabolic lag interpolation',
            'window_ms':1000*n/rate,'hop_ms':1000*hop/rate,'window_half_width_ms':500*n/rate,
            'fmin_hz':fmin,'fmax_hz':fmax,'minimum_confidence':min_confidence,
            'confidence_meaning':'Periodicity heuristic, not probability of correct pitch',
            'scope':'Independent channels; assumes one pitched voice; no imputation or octave correction','channels':channels}


def _envelope(x,rate,frame_ms):
    np=_numpy();n=max(1,round(rate*frame_ms/1000));pad=(-len(x))%n
    return np.sqrt(np.mean(np.pad(x,((0,pad),(0,0))).reshape(-1,n,x.shape[1])**2,axis=1)),n/rate


def _segments(values,threshold,step):
    np=_numpy();mask=values>threshold;changes=np.diff(np.pad(mask.astype(int),(1,1)))
    return [(float(a*step),float(b*step)) for a,b in zip(np.flatnonzero(changes==1),np.flatnonzero(changes==-1))]


def _harmonics(x,rate,f0,count):
    np=_numpy();count=min(count,int((rate/2-1)/f0));t=np.arange(len(x))/rate
    matrix=np.column_stack([np.ones(len(t)),*[v for n in range(1,count+1) for v in (np.cos(2*np.pi*n*f0*t),np.sin(2*np.pi*n*f0*t))]])
    coefficients=np.linalg.lstsq(matrix,x,rcond=None)[0];amps=np.sqrt(coefficients[1::2]**2+coefficients[2::2]**2)
    return [{'harmonic':i+1,'channels':[{'amplitude':float(a),
              'relative_to_fundamental_db':_db(a/max(float(amps[0,ch]),1e-15)) if amps[0,ch]>1e-10 else None}
             for ch,a in enumerate(row)]} for i,row in enumerate(amps)]


def analyze(path,purpose='overview',request=None,reference=None,detail=False):
    np=_numpy();request=request or {}
    common={'start_seconds','end_seconds'}
    allowed={'overview':set(),'pitch':{'min_hz','max_hz','window_ms','hop_ms','minimum_confidence','floor_dbfs','max_points','monophonic'},
             'envelope':{'note_on_seconds','note_off_seconds','next_on_seconds','frame_ms','threshold_db'},
             'harmonics':{'fundamental_hz','harmonics'},'delay':{'frame_ms','expected_delay_seconds'}}
    if purpose not in allowed or not isinstance(request,dict) or set(request)-common-allowed[purpose]:raise ValueError('Unknown analysis purpose/request field')
    for key,value in request.items():
        if key=='monophonic':
            if type(value) is not bool:raise ValueError('monophonic must be boolean')
        elif type(value) not in (int,float) or not math.isfinite(value):raise ValueError(f'{key} must be a finite number')
    rate,whole=load(path);start=request.get('start_seconds',0.);end=request.get('end_seconds',len(whole)/rate)
    if not 0<=start<end<=len(whole)/rate+.000001:raise ValueError('Choose a measurement window within the WAV')
    x=whole[round(start*rate):round(end*rate)]
    if not len(x):raise ValueError('Measurement window contains no PCM frames')
    if len(x)>rate*120:raise ValueError('Analyze an excerpt of at most 120 seconds; select start_seconds/end_seconds')
    result={'purpose':purpose,'input':str(Path(path).resolve()),'measurement_window_seconds':[start,end],
            'sample_rate':rate,'channels':x.shape[1],'usability':'usable','reason_code':None,
            'conclusion_scope':'Signal observations and explicit hypotheses; no listening, preference or quality score'}
    if purpose=='overview':
        peak=float(np.max(np.abs(x)));rms=float(np.sqrt(np.mean(x*x)));freq,power=_spectrum(rate,x);profile=power.mean(axis=0);total=max(float(profile.sum()),1e-30)
        result['observations']={'peak_dbfs':_db(peak),'rms_dbfs':_db(rms),'crest_db':_db(peak/max(rms,1e-15)),
            'over_full_scale_samples':int(np.sum(np.abs(x)>1)),'near_full_scale_samples':int(np.sum(np.abs(x)>=.9999)),
            'band_energy_fractions':[{'low_hz':lo,'high_hz':hi,'fraction':float(profile[(freq>=lo)&(freq<hi)].sum()/total)} for lo,hi in BANDS]}
        if x.shape[1]==2:
            mid=(x[:,0]+x[:,1])/2;side=(x[:,0]-x[:,1])/2
            denom=float(np.sqrt(np.sum(x[:,0]**2)*np.sum(x[:,1]**2)))
            result['observations']['stereo']={'correlation':float(np.sum(x[:,0]*x[:,1])/denom) if denom else None,
                'side_to_mid_db':_db(np.sqrt(np.mean(side**2)))-_db(np.sqrt(np.mean(mid**2))),
                'mono_rms_dbfs':_db(np.sqrt(np.mean(mid**2)))}
        result['limits']=['Full-scale samples alone do not prove clipping (native Normalize deliberately reaches 0dBFS).',
                          'Band energy/stereo measures do not establish audibility, taste or arrangement fit.']
    elif purpose=='pitch':
        kwargs={target:request[source] for source,target in [('min_hz','fmin'),('max_hz','fmax'),('window_ms','window_ms'),('hop_ms','hop_ms'),
                ('minimum_confidence','min_confidence'),('floor_dbfs','floor_dbfs'),('max_points','max_points')] if source in request}
        data=pitch_trace(x,rate,detail=detail,**kwargs)
        for channel in data['channels']:
            for row in channel.get('frames',channel['summary']):row['seconds']+=start
        result['observations']=data
        if not request.get('monophonic'):
            result.update(usability='ambiguous',reason_code='monophonic_context_not_confirmed',
                          next_experiment='Use a solo single-voice interval and set monophonic=true only when the project notes support it. Octave layers can share a strong waveform period.')
        elif not any(c['tracked_frame_count'] for c in data['channels']):
            result.update(usability='unavailable',reason_code='no_unambiguous_periodic_frames',next_experiment='Inspect silence/noise or bounds; enlarge the window for lower pitches. Do not fill nulls.')
        result['limits']=['Periodicity cannot separate a harmonic-rich voice from overlapping octave voices.',
                          'Frame center ± half-window is the timing resolution; hop size is not onset precision.']
    elif purpose=='envelope':
        frame_ms=request.get('frame_ms',20.)
        if not 2<=frame_ms<=200:raise ValueError('frame_ms must be 2..200')
        env,step=_envelope(x,rate,frame_ms);on=request.get('note_on_seconds',start)-start;off=request.get('note_off_seconds');next_on=request.get('next_on_seconds',end)
        if not 0<=on<len(x)/rate or off is not None and not start+on<=off<=next_on<=end+.000001:raise ValueError('Invalid note-on/off/next-on bounds')
        threshold_db=request.get('threshold_db',-40.)
        if not -100<=threshold_db<0:raise ValueError('threshold_db must be -100..0 exclusive at 0')
        rows=[]
        for ch in range(env.shape[1]):
            curve=env[:,ch];begin=min(len(curve)-1,int(on/step));stop=min(len(curve),max(begin+1,int(((off-start) if off is not None else len(x)/rate)/step)))
            peak=float(np.max(curve[begin:stop]));at10=np.flatnonzero(curve[begin:stop]>=peak*.1);at90=np.flatnonzero(curve[begin:stop]>=peak*.9)
            row={'channel':ch,'frame_seconds':step,'peak_rms_dbfs':_db(peak),'attack_10_to_90_seconds':float((at90[0]-at10[0])*step) if peak and len(at10) and len(at90) else None}
            if off is not None:
                tail=curve[int((off-start)/step):min(len(curve),int((next_on-start)/step))];above=np.flatnonzero(tail>peak*10**(threshold_db/20))
                row.update(note_off_seconds=off,tail_above_relative_threshold_seconds=float((above[-1]+1)*step) if len(above) else 0.,
                           threshold_relative_db=threshold_db,tail_truncated_by_next_on_or_window=bool(len(above) and above[-1]==len(tail)-1),
                           pre_next_50ms_rms_dbfs=_db(np.sqrt(np.mean(x[max(0,round((next_on-start-.05)*rate)):round((next_on-start)*rate),ch]**2))))
            rows.append(row)
        result['observations']=rows
        if not any(r['peak_rms_dbfs']>-100 for r in rows):
            result.update(usability='unavailable',reason_code='note_interval_silent',next_experiment='Check note timing, target routing and mute state before measuring attack or release.')
        elif off is None:result.update(usability='ambiguous',reason_code='note_off_required_for_release',next_experiment='Provide actual note_on_seconds/note_off_seconds/next_on_seconds from the excerpt.')
        result['limits']=['RMS frame smoothing limits transient precision. Overlapping voices/reverb affect the apparent release; isolate the target before attributing it to one envelope.']
    else:
        if reference is None:raise ValueError(f'{purpose} requires --reference with a controlled dry/before WAV')
        other_rate,whole_ref=load(reference)
        if rate!=other_rate or x.shape[1]!=whole_ref.shape[1] or len(whole_ref)<round(end*rate):raise ValueError('Reference needs the same rate/channels and complete measurement window')
        dry=whole_ref[round(start*rate):round(end*rate)];result['reference']=str(Path(reference).resolve())
        if purpose=='harmonics':
            gains=np.sum(dry*x,axis=0)/np.maximum(np.sum(dry*dry,axis=0),1e-30);residual=x-dry*gains
            ratios=np.sqrt(np.mean(residual**2,axis=0))/np.maximum(np.sqrt(np.mean(x*x,axis=0)),1e-15)
            observations={'gain_fit':[{'channel':ch,'gain':float(g),'gain_db':_db(abs(g)),
                         'residual_relative_db':_db(ratios[ch]),'constant_gain_within_minus60db':bool(ratios[ch]<=.001)} for ch,g in enumerate(gains)]}
            f0=request.get('fundamental_hz');count=request.get('harmonics',8)
            if f0 is not None:
                if len(x)>rate*5:raise ValueError('Choose a stationary interval of at most five seconds for harmonic fitting')
                if not 0<f0<rate/2 or type(count) is not int or not 1<=count<=32:raise ValueError('Invalid fundamental_hz/harmonics')
                if len(x)*f0/rate<3:raise ValueError('Harmonic fitting needs at least three fundamental periods in a stationary note window')
                observations.update(fundamental_hz=f0,before=_harmonics(dry,rate,f0,count),after=_harmonics(x,rate,f0,count))
            else:result.update(usability='ambiguous',reason_code='stationary_fundamental_required',next_experiment='Choose a single sustained note interval and supply its measured fundamental_hz. Gain-fit remains valid for aligned PCM.')
            result['observations']=observations
            if float(np.mean(dry*dry))<1e-15:
                result.update(usability='unavailable',reason_code='reference_window_silent',next_experiment='Choose a voiced dry/reference interval before comparing gain or harmonic ratios.')
            result['limits']=['A gain-fit residual can also come from phase, latency, tuning, modulation or randomness; compare repeated unchanged renders.',
                              'Relative harmonics require a stationary single voice. More harmonics is not a quality score.']
        else:
            frame_ms=request.get('frame_ms',5.)
            if not 1<=frame_ms<=50:raise ValueError('Delay frame_ms must be 1..50')
            if request.get('expected_delay_seconds',1)<=0:raise ValueError('expected_delay_seconds must be positive')
            a,step=_envelope(dry,rate,frame_ms);b,_=_envelope(x,rate,frame_ms)
            a=np.sqrt(np.mean(a*a,axis=1));b=np.sqrt(np.mean(b*b,axis=1))
            dry_events=_segments(a,max(float(a.max())*.1,1e-8),step);wet_events=_segments(b,max(float(b.max())*.06,1e-8),step)
            rows=[]
            for on,off in wet_events:
                chunk=x[round(on*rate):round(off*rate)]
                rows.append({'on_seconds':start+on,'off_seconds':start+off,'channel_rms_dbfs':[_db(v) for v in np.sqrt(np.mean(chunk**2,axis=0))]})
            if len(dry_events)!=1:
                result.update(usability='ambiguous',reason_code='isolated_input_pulse_required',next_experiment='Render one short dry note/impulse followed by silence; dense music cannot uniquely identify an echo interval.')
            delays=[on-dry_events[0][0] for on,off in wet_events if on-dry_events[0][0]>step*2] if dry_events else []
            intervals=np.diff(delays)
            result['observations']={'frame_seconds':step,'dry_activity_segments':dry_events,'wet_activity_segments':rows,
                  'positive_onset_delays_seconds':delays[:16],'median_echo_spacing_seconds':float(np.median(intervals)) if len(intervals) else None,
                  'expected_delay_seconds':request.get('expected_delay_seconds')}
            if not delays:result.update(usability='unavailable',reason_code='no_separated_echo_onsets',next_experiment='Shorten the input, extend silence, lower feedback, and use sufficient wet level before measuring echo spacing.')
            result['limits']=['Envelope thresholds/frame width introduce onset uncertainty. Dense or self-oscillating material is ambiguous; no taste or perceived-space conclusion.']
    return result


def register(app,emit,json_option):
    import click
    from .contracts import Result
    from .json_output import decode_json,canonical_json
    @app.commands['audio'].command('analyze')
    @click.option('--input','source',required=True,type=click.Path(path_type=Path))
    @click.option('--purpose',default='overview',type=click.Choice(['overview','pitch','envelope','harmonics','delay']))
    @click.option('--reference',type=click.Path(path_type=Path))
    @click.option('--request',type=click.Path(path_type=Path))
    @click.option('--output',type=click.Path(path_type=Path))
    @click.option('--detail',is_flag=True,help='Include full pitch frames; normally save these to --output.')
    @json_option
    def command(source,purpose,reference,request,output,detail):
        if output is not None and (output.exists() or not output.parent.is_dir()):raise ValueError('Choose a new analysis JSON output')
        data=analyze(source,purpose,decode_json(request.read_text(encoding='utf-8-sig')) if request else None,reference,detail)
        if output is not None:
            output.write_text(canonical_json(data)+'\n',encoding='utf8')
            summary={k:v for k,v in data.items() if k!='observations'}
            summary.update(output=str(output.resolve()),observations_omitted='Saved in analysis JSON; read only the needed purpose/channel/window.')
        else:summary=data
        emit(Result(command='audio analyze',status='verified' if data['usability']=='usable' else 'unknown',
                    reason_code=data.get('reason_code'),verified_scopes=['signal_'+purpose] if data['usability']=='usable' else [],data=summary))
