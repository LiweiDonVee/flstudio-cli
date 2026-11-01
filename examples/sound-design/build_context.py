"""Rebuild the authored 110BPM/96-note acceptance excerpt with local plugins.

uv run python examples/sound-design/build_context.py --output-dir NEW_DIRECTORY
Requires the local Sytrus Default and installed Surge XT FST; bundles no plugin.
"""
from pathlib import Path
import argparse
import json
import shutil

from flstudio_cli.flp import create_project

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir',type=Path,required=True)
parser.add_argument('--fl-install',type=Path,default=Path('C:/Program Files/Image-Line/FL Studio 2026'))
parser.add_argument('--surge-preset',type=Path,default=Path.home()/'Documents/Image-Line/FL Studio/Presets/Plugin database/Installed/Generators/VST3/Surge XT.fst')
args=parser.parse_args()
root,install=args.output_dir.resolve(),args.fl_install.resolve()
sytrus=install/'Data/Patches/Plugin presets/Generators/Sytrus/Default.fst'
template=install/'Data/Templates/Minimal/Basic/Basic.flp'
repo=Path(__file__).resolve().parents[2]
samples=[repo/'examples/audio'/name for name in ('kick.wav','clap.wav','hat.wav')]
for file in [sytrus,template,args.surge_preset,*samples]:
    if not file.is_file(): parser.error(f'Required installed preset/template or authored sample is missing: {file}')
if root.exists() or not root.parent.is_dir(): parser.error('Choose a new output directory with an existing parent')
root.mkdir();(root/'assets').mkdir()
for sample in samples: shutil.copyfile(sample,root/'assets'/sample.name)

def note(key,start,length,velocity=90):
    return {'key':key,'start_tick':start,'length_tick':length,'velocity':velocity}

bass=[];lead=[];pads=[]
for bar,fundamental in enumerate([24,20,27,22]):
    at=bar*384
    bass.extend([note(fundamental,at,120,96),note(fundamental+12,at+144,30,72),note(fundamental+7,at+240,72,84)])
    for off,key,velocity in [(0,48,88),(72,55,68),(168,58,105),(288,55,78)]:
        lead.append(note(key+(fundamental-24)%12,at+off,48,velocity))
    pads.extend(note(fundamental+24+interval,at,336,62) for interval in (0,3,7))
kick=[note(60,start,24,100) for start in range(0,1536,96)]
clap=[note(60,bar*384+off,24,80) for bar in range(4) for off in (96,288)]
hat=[note(60,start,12,55 if (start//48)%2 else 72) for start in range(0,1536,48)]
spec={'tempo_bpm':110,'channels':[
    {'name':'Bass target','plugin_preset':str(sytrus),'mixer_track':1,'volume_raw':6000},
    {'name':'Lead target','plugin_preset':str(sytrus),'mixer_track':2,'volume_raw':5000},
    {'name':'Pad target','plugin_preset':str(args.surge_preset.resolve()),'mixer_track':3,'volume_raw':3800},
    *[{'name':label,'sample_path':str(root/'assets'/file),'mixer_track':i+4,'volume_raw':volume}
      for i,(label,file,volume) in enumerate([('Kick','kick.wav',8000),('Clap','clap.wav',6000),('Hat','hat.wav',4600)])]],
    'patterns':[{'number':1,'name':'Actual 4-bar phrase','scores':[
        {'channel_index':i,'notes':notes} for i,notes in enumerate((bass,lead,pads,kick,clap,hat))]}],
    'playlist':[{'pattern_number':1,'track':1,'start_tick':0,'length_tick':1536}],
    'mixer':[{'track':i,'name':name,'routes':[0]} for i,name in enumerate(['BASS','LEAD','PAD','KICK','CLAP','HAT'],start=1)]}
(root/'request.json').write_text(json.dumps(spec,indent=2)+'\n',encoding='utf8')
create_project(spec,template).save(root/'context.flp')
print(root/'context.flp')
