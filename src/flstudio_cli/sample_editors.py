"""Edison/Slicex embedded WAV assets and standard cue/region metadata.

This does not decode an entire audio editor. It replaces its length-tagged RIFF
payload while retaining native articulation, UI, routing and unknown state.
"""
from pathlib import Path
import math
import struct


def _chunk(tag,body):
    return tag+struct.pack('<I',len(body))+body+(b'\0' if len(body)%2 else b'')


def chunks(wav):
    if wav[:4]!=b'RIFF' or wav[8:12]!=b'WAVE' or struct.unpack_from('<I',wav,4)[0]+8!=len(wav):
        raise ValueError('Expected a complete RIFF/WAVE payload')
    at=12;result=[]
    while at<len(wav):
        if at+8>len(wav):raise ValueError('Truncated WAV chunk')
        n=struct.unpack_from('<I',wav,at+4)[0];end=at+8+n
        if end>len(wav):raise ValueError('WAV chunk extends past its payload')
        result.append((wav[at:at+4],wav[at+8:end]));at=end+(n%2)
    return result


def payloads(name,data):
    if name=='Edison':
        if data[:4]==struct.pack('<I',4):candidates=[16]
        elif data[:4]==bytes.fromhex('03000d00'):candidates=[24]
        else:raise ValueError('Unsupported Edison state family')
    elif name=='Slicex':
        if data[:4] not in (bytes.fromhex('03000600'),bytes.fromhex('03000700')):raise ValueError('Unsupported Slicex state family')
        candidates=[];at=0
        while True:
            at=data.find(b'RIFF',at)
            if at<0:break
            if at>=4 and at+12<=len(data):
                size=struct.unpack_from('<I',data,at+4)[0]+8
                if struct.unpack_from('<I',data,at-4)[0]==size and at+size<=len(data) and data[at+8:at+12]==b'WAVE':
                    candidates.append(at);at+=size;continue
            at+=4
    else:raise ValueError('Sample editing supports Edison and Slicex')
    result=[]
    for at in candidates:
        if data[at:at+4]!=b'RIFF':raise ValueError('Native sample payload is missing')
        size=struct.unpack_from('<I',data,at+4)[0]+8
        width=8 if name=='Edison' and at==24 else 4
        if int.from_bytes(data[at-width:at],'little')!=size or at+size>len(data):raise ValueError('Native WAV length disagrees with RIFF')
        wav=data[at:at+size];chunks(wav);result.append((at,wav))
    if len(result)!=(1 if name=='Edison' else 2):raise ValueError('Unsupported editor payload count')
    return result


def decode(wav):
    from .sound_audio import _numpy
    np=_numpy()
    parts=dict(chunks(wav));fmt=parts.get(b'fmt ',b'');pcm=parts.get(b'data')
    if len(fmt)<16 or pcm is None:raise ValueError('WAV requires fmt and data')
    tag,channels,rate,byte_rate,align,bits=struct.unpack_from('<HHIIHH',fmt)
    if not 1<=channels<=8 or not 8000<=rate<=384000 or bits not in (16,24,32) or align!=channels*(bits//8) or len(pcm)%align:
        raise ValueError('Unsupported or inconsistent WAV format')
    if tag==3 and bits==32:values=np.frombuffer(pcm,dtype='<f4').copy()
    elif tag==1 and bits==16:values=np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768
    elif tag==1 and bits==24:
        b=np.frombuffer(pcm,dtype=np.uint8).reshape(-1,3);v=b[:,0].astype(np.int32)|(b[:,1].astype(np.int32)<<8)|(b[:,2].astype(np.int32)<<16)
        values=((v^0x800000)-0x800000).astype(np.float32)/8388608
    elif tag==1 and bits==32:values=np.frombuffer(pcm,dtype='<i4').astype(np.float32)/2147483648
    else:raise ValueError('Supported audio: PCM16/24/32 or IEEE float32 WAV')
    if not np.isfinite(values).all():raise ValueError('Audio contains non-finite samples')
    return values.reshape(-1,channels),rate


def regions(wav,frames):
    parts=chunks(wav);cue=next((v for k,v in parts if k==b'cue '),None);rows=[]
    if cue is None:return rows
    if len(cue)<4:raise ValueError('Truncated WAV cue data')
    count=struct.unpack_from('<I',cue)[0]
    if len(cue)!=4+count*24:raise ValueError('Unsupported WAV cue record count')
    names={};lengths={}
    for key,value in parts:
        if key!=b'LIST' or value[:4]!=b'adtl':continue
        at=4
        while at+8<=len(value):
            tag=value[at:at+4];n=struct.unpack_from('<I',value,at+4)[0];body=value[at+8:at+8+n]
            if len(body)!=n:raise ValueError('Truncated WAV region metadata')
            if tag==b'labl' and n>=4:names[struct.unpack_from('<I',body)[0]]=body[4:].rstrip(b'\0').decode('utf8',errors='replace')
            if tag==b'ltxt' and n>=8:lengths[struct.unpack_from('<I',body)[0]]=struct.unpack_from('<I',body,4)[0]
            at+=8+n+n%2
    for i in range(count):
        ident,position,tag,start,block,offset=struct.unpack_from('<II4sIII',cue,4+i*24)
        if tag!=b'data' or offset>frames:raise ValueError('WAV cue does not reference an admitted sample position')
        rows.append({'id':ident,'name':names.get(ident,f'Slice {i+1}'),'start_frame':offset})
    rows.sort(key=lambda x:x['start_frame'])
    for i,row in enumerate(rows):
        row['end_frame']=min(frames,row['start_frame']+lengths[row['id']]) if row['id'] in lengths else (rows[i+1]['start_frame'] if i+1<len(rows) else frames)
        row['expected_import_key']=60+i
    return rows


def _make_wav(samples,rate,template,region_list):
    channels=samples.shape[1];frames=len(samples)
    fmt=struct.pack('<HHIIHH',3,channels,rate,rate*channels*4,channels*4,32)
    parts=[_chunk(b'fmt ',fmt),_chunk(b'data',samples.astype('<f4').tobytes())]
    for tag,value in chunks(template):
        if tag not in (b'fmt ',b'data',b'cue ') and not (tag==b'LIST' and value[:4]==b'adtl'):parts.append(_chunk(tag,value))
    if region_list:
        if len(region_list)>72:raise ValueError('This ordered import supports at most 72 regions at native keys 60..131; custom key maps require the native editor')
        cues=[];adtl=[];last=-1
        for i,row in enumerate(region_list):
            if not isinstance(row,dict) or not {'start_frame','end_frame'}<=set(row) or set(row)-{'start_frame','end_frame','name','key'}:raise ValueError('Regions require start_frame/end_frame and optional name/key')
            start,end=row['start_frame'],row['end_frame'];name=row.get('name',f'Slice {i+1}')
            if type(start) is not int or type(end) is not int or not last<start<end<=frames:raise ValueError('Regions must be ordered, nonempty and within the audio')
            if row.get('key',60+i)!=60+i:raise ValueError('This Slicex import maps ordered regions to keys 60,61,...; arbitrary trigger maps are not yet supported')
            if not isinstance(name,str) or not name or '\0' in name:raise ValueError('Region name must be nonempty text')
            ident=i+1;cues.append(struct.pack('<II4sIII',ident,start,b'data',0,0,start))
            adtl.extend([_chunk(b'labl',struct.pack('<I',ident)+name.encode('utf8')+b'\0'),
                         _chunk(b'ltxt',struct.pack('<II4sHHHH',ident,end-start,b'rgn ',0,0,0,65001))]);last=start
        parts.extend([_chunk(b'cue ',struct.pack('<I',len(cues))+b''.join(cues)),_chunk(b'LIST',b'adtl'+b''.join(adtl))])
    body=b'WAVE'+b''.join(parts)
    return b'RIFF'+struct.pack('<I',len(body))+body


def describe(name,data):
    from .sound_audio import _numpy
    np=_numpy()
    result=[]
    for i,(at,wav) in enumerate(payloads(name,data)):
        samples,rate=decode(wav);frames=len(samples)
        result.append({'deck':'a' if i==0 else 'b','frames':frames,'sample_rate':rate,'channels':samples.shape[1],
                       'peak':float(np.max(np.abs(samples))) if frames else 0.,
                       'rms':float(np.sqrt(np.mean(samples.astype(np.float64)**2))) if frames else 0.,
                       'regions':regions(wav,frames),'asset_storage':'embedded in native FLP state'})
    return {'plugin':name,'audio':result,'limitations':['This adapter edits length-tagged embedded WAV data, not every editor tool or Slicex articulator.',
            'expected_import_key is the ordered Default-family import convention (60,61,...), not an observation of arbitrary saved Slicex trigger maps; verify the rendered slice phrase.',
            'Trim/gain/normalization here are deterministic CLI PCM edits; native editor processing must be identified separately.']}


def edit(name,data,request):
    from .sound_audio import _numpy
    np=_numpy()
    allowed={'audio_file','deck','trim_frames','gain_db','normalize_peak_dbfs','regions'}
    if not isinstance(request,dict) or not request or set(request)-allowed:raise ValueError('Unknown sample-editor design field')
    deck=request.get('deck','a')
    if deck not in ('a','b') or name=='Edison' and deck!='a':raise ValueError('Choose an available audio deck')
    index=0 if deck=='a' else 1;at,old=payloads(name,data)[index]
    wave=Path(request['audio_file']).read_bytes() if request.get('audio_file') else old
    samples,rate=decode(wave)
    if len(samples)>rate*120:raise ValueError('Sample-editor tasks are bounded to 120 seconds per asset')
    existing=[{k:v for k,v in row.items() if k not in ('id','expected_import_key')} for row in regions(wave,len(samples))]
    if 'trim_frames' in request:
        span=request['trim_frames']
        if not isinstance(span,list) or len(span)!=2 or any(type(v) is not int for v in span) or not 0<=span[0]<span[1]<=len(samples):raise ValueError('trim_frames must select [start,end) within the audio')
        samples=samples[span[0]:span[1]].copy();existing=[]
    if not len(samples):raise ValueError('Load or retain nonempty audio before processing')
    if 'gain_db' in request:
        from .native_curves import number
        samples=samples*(10**(number(request['gain_db'],-60,24,'gain_db')/20))
    if 'normalize_peak_dbfs' in request:
        from .native_curves import number
        peak=float(np.max(np.abs(samples)))
        if peak==0:raise ValueError('Cannot peak-normalize silence')
        samples=samples*(10**(number(request['normalize_peak_dbfs'],-60,0,'normalize_peak_dbfs')/20)/peak)
    region_list=request.get('regions',existing)
    if not isinstance(region_list,list):raise ValueError('regions must be an explicit array')
    # Native sample data is embedded; no dependence on the source pathname.
    new=_make_wav(samples,rate,wave,region_list)
    width=8 if name=='Edison' and at==24 else 4
    return data[:at-width]+len(new).to_bytes(width,'little')+new+data[at+len(old):]


def equivalent(name,left,right):
    from .sound_audio import _numpy
    np=_numpy()
    for (_,a),(_,b) in zip(payloads(name,left),payloads(name,right)):
        x,sr=decode(a);y,other=decode(b)
        if sr!=other or not np.array_equal(x,y) or regions(a,len(x))!=regions(b,len(y)):return False
    return True


def export(name,data,output,deck='a'):
    output=Path(output)
    if output.exists() or not output.parent.is_dir():raise ValueError('Choose a new WAV output in an existing directory')
    if deck not in ('a','b') or name=='Edison' and deck!='a':raise ValueError('Choose an available audio deck')
    wav=payloads(name,data)[0 if deck=='a' else 1][1]
    if not len(decode(wav)[0]):raise ValueError('Editor has no embedded audio to export')
    output.write_bytes(wav)
    return {'output':str(output.resolve()),'scope':'exact embedded native WAV, including cue/region metadata'}
