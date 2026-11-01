"""Scoped native transfer curves: Maximus and Fruity WaveShaper.

Only calibrated FL26/factory serialization families are admitted. X is stored
as a segment delta; public points use absolute X. Unedited banks/control bytes
and envelope trailers are retained, including Maximus' spare A/B state.
"""
import math
import struct

NODE=struct.Struct('<ddfI')
BANDS=('low','mid','high','master')


def number(value,lo,hi,name):
    if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:
        raise ValueError(f'{name} must be a finite number {lo}..{hi}')
    return float(value)


def _blocks(name,data):
    if name=='Maximus':
        prefix=data[:4].hex()
        if prefix not in ('03000e00','03000f00'):raise ValueError('Unsupported Maximus native state layout')
        at=539 if prefix=='03000e00' else 543
        count,legacy=8,False
    elif name=='Fruity WaveShaper':
        if data[:4].hex() not in ('01000000','03000400'):raise ValueError('Unsupported WaveShaper native state layout')
        at,count,legacy=22,1,data[:4]==bytes.fromhex('01000000')
    else:raise ValueError('Curve editing supports Maximus or Fruity WaveShaper')
    blocks=[]
    for index in range(count):
        start=at
        if at+12>len(data):raise ValueError('Truncated transfer curve header')
        version,flags,n=struct.unpack_from('<3i',data,at)
        if version!=3 or flags!=(0 if legacy else 3) or not 2<=n<=128:
            raise ValueError('Unsupported transfer curve envelope')
        size=12 if legacy else NODE.size;at+=12;points=[];x=0.
        for i in range(n):
            if at+size>len(data):raise ValueError('Truncated transfer curve point')
            if legacy:dx,y,t=struct.unpack_from('<fff',data,at);point_flags=0
            else:dx,y,t,point_flags=NODE.unpack_from(data,at)
            x+=number(dx,0,1,'Segment width');number(y,0,1,'Curve Y');number(t,-1,1,'Curve tension')
            if x>1.00001:raise ValueError('Transfer curve extends beyond its admitted domain')
            points.append({'x':x,'y':y,'tension':t,'flags_raw':point_flags});at+=size
        if data[at:at+20]!=b'\0'*4+b'\xff'*16:raise ValueError('Unsupported transfer curve trailer')
        at+=20
        blocks.append({'index':index,'start':start,'end':at,'legacy':legacy,'points':points,'header':(version,flags,n)})
    # WaveShaper appends calibrated native option bytes; Maximus ends at bank 8.
    if name=='Maximus' and at!=len(data):raise ValueError('Unexpected Maximus trailing private state')
    if name=='Fruity WaveShaper' and len(data)-at not in (0,6):raise ValueError('Unsupported WaveShaper option trailer')
    return blocks


def describe(name,data):
    blocks=_blocks(name,data)
    if name=='Maximus':
        return {'plugin':name,'bands':{band:{'points':[{k:v for k,v in p.items() if k!='flags_raw'} for p in blocks[i*2]['points']]}
                                      for i,band in enumerate(BANDS)},
                'coordinate_units':'normalized native log-level graph, not linear amplitude or asserted dB',
                'spare_banks_preserved':True,
                'limitations':['Default-derived FL26 transfer curves only; spare banks are preserved, not an A/B-bank selector.',
                               'Band timing, crossovers and gain require addressed host controls; graph coordinates are not physical dB.']}
    return {'plugin':name,'points':[{k:v for k,v in p.items() if k!='flags_raw'} for p in blocks[0]['points']],
            'coordinate_units':'normalized input/output graph; polarity mode is retained',
            'controls_raw':dict(zip(('pre','mix','post'),struct.unpack_from('<3i',data,4))),
            'limitations':['Default-derived native curve and drive/mix/post controls; existing polarity/oversampling mode is retained.',
                           'A curve knee outside the actual input range can change only gain; verify a controlled dry render.']}


def edit(name,data,request):
    if not isinstance(request,dict) or not request:raise ValueError('Curve design must be an object')
    blocks=_blocks(name,data);updates={}
    if name=='Maximus':
        if set(request)!={'bands'} or not isinstance(request['bands'],dict) or not request['bands'] or set(request['bands'])-set(BANDS):
            raise ValueError('Maximus design requires bands: low/mid/high/master')
        for band,spec in request['bands'].items():
            if not isinstance(spec,dict) or set(spec)!={'points'}:raise ValueError('Each Maximus band requires points')
            updates[BANDS.index(band)*2]=spec['points']
    else:
        if set(request)-{'points','pre_raw','mix_raw','post_raw'}:raise ValueError('WaveShaper accepts points and pre_raw/mix_raw/post_raw')
        if 'points' in request:updates[0]=request['points']
        mutable=bytearray(data)
        for key,at,hi in [('pre_raw',4,256),('mix_raw',8,128),('post_raw',12,128)]:
            if key in request:
                value=request[key]
                if type(value) is not int or not 0<=value<=hi:raise ValueError(f'{key} must be integer 0..{hi}')
                struct.pack_into('<i',mutable,at,value)
        data=bytes(mutable)
    for index,points in updates.items():
        if not isinstance(points,list) or not 2<=len(points)<=64:raise ValueError('A curve needs 2..64 explicit points')
        old=blocks[index];body=[];previous=0.
        for i,point in enumerate(points):
            if not isinstance(point,dict) or not {'x','y'}<=set(point) or set(point)-{'x','y','tension'}:
                raise ValueError('Curve points require x/y and optional tension')
            x=number(point['x'],0,1,'Curve X');y=number(point['y'],0,1,'Curve Y');t=number(point.get('tension',0),-1,1,'Tension')
            if (i==0 and x!=0) or (i and x<=previous) or (i==len(points)-1 and x!=1):
                raise ValueError('Curve X must increase strictly from 0 to 1')
            # Same native straight/curve segment type as the calibrated default;
            # selection bits are UI state, not a new interpolation choice.
            flags=(old['points'][i]['flags_raw'] & ~0x10000) if i<len(old['points']) else 0x02000000
            body.append(struct.pack('<fff',x-previous,y,t) if old['legacy'] else NODE.pack(x-previous,y,t,flags))
            previous=x
        updates[index]=struct.pack('<3i',old['header'][0],old['header'][1],len(points))+b''.join(body)+b'\0'*4+b'\xff'*16
    for index in sorted(updates,reverse=True):
        block=blocks[index];data=data[:block['start']]+updates[index]+data[block['end']:]
    describe(name,data)
    return data
