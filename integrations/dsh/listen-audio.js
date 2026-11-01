import {createHash} from 'node:crypto'
import {isAbsolute} from 'node:path'

export const name='flstudio-native-audio-listener'
export const inject=['tools','fs','credentials']
const sha=bytes=>createHash('sha256').update(bytes).digest('hex')
const textResult=value=>[{type:'text',text:JSON.stringify(value)}]

async function readFile(ctx,exec,path,cap){
 if(typeof path!=='string'||!isAbsolute(path))throw Error('Use an absolute manifest/audio path')
 const target=await ctx.fs.resolve(path,{signal:exec.signal})
 const info=await ctx.fs.stat(target,exec.signal)
 if(!info||info.type!=='file')throw Error('The addressed audio artifact is not a regular readable file')
 return Buffer.from(await ctx.fs.readBytes(target,exec.signal,cap))
}

async function artifact(ctx,exec,path,id,cap){
 const manifest=JSON.parse((await readFile(ctx,exec,path,2_000_000)).toString('utf8'))
 let selected
 if(['flstudio.audio.preview','flstudio.sound-design.comparison'].includes(manifest.kind)){
  if(manifest.status!=='ready')throw Error('Preview is not ready; inspect its native render failure first')
  selected=manifest.artifacts.find(a=>a.id===(id??manifest.listening_artifact_id??'audio'))
 }else if(manifest.kind==='flstudio.sound-design.audition'){
  const receipt=manifest.renders?.[id??'context-1']
  if(receipt?.status!=='verified')throw Error('Selected audition render is not verified')
  selected={id:id??'context-1',path:receipt.output,sha256:receipt.audio.sha256,
   mime_type:'audio/wav',duration_seconds:receipt.audio.duration_seconds,
   source_start_seconds:0,source_end_seconds:receipt.audio.duration_seconds}
 }else throw Error('Use a CLI audio preview or sound-design audition manifest')
 if(!selected)throw Error('Artifact id is absent from this manifest')
 if(!['audio/wav','audio/mpeg','audio/mp3','audio/flac','audio/ogg'].includes(selected.mime_type))throw Error('Unsupported listening MIME type')
 if(!Number.isFinite(selected.duration_seconds)||selected.duration_seconds<=0)throw Error('Artifact duration is missing or invalid')
 const bytes=await readFile(ctx,exec,selected.path,cap)
 if(!bytes.length||sha(bytes)!==selected.sha256)throw Error('Audio bytes do not match their manifest SHA256; rebuild the preview')
 if(selected.bytes!==undefined&&selected.bytes!==bytes.length)throw Error('Audio byte size differs from its manifest')
 const signature=bytes.subarray(0,12)
 const valid=(selected.mime_type==='audio/wav'&&signature.toString('ascii',0,4)==='RIFF'&&signature.toString('ascii',8,12)==='WAVE')||
  (['audio/mpeg','audio/mp3'].includes(selected.mime_type)&&(signature.toString('ascii',0,3)==='ID3'||signature[0]===0xff&&(signature[1]&0xe0)===0xe0))||
  (selected.mime_type==='audio/flac'&&signature.toString('ascii',0,4)==='fLaC')||
  (selected.mime_type==='audio/ogg'&&signature.toString('ascii',0,4)==='OggS')
 if(!valid)throw Error('Artifact bytes do not have the declared audio container signature')
 return {bytes,input:{artifact_id:selected.id,sha256:selected.sha256,bytes:bytes.length,
  mime_type:selected.mime_type,duration_seconds:selected.duration_seconds,
  coverage:{start_seconds:selected.source_start_seconds??0,end_seconds:selected.source_end_seconds??selected.duration_seconds,
   basis:'Entire selected audio artifact transmitted; this does not certify that the model attended to every moment'},
  conversion:selected.conversion??null}}
}

export async function evaluateAudio(ctx,config,args,exec){
 const listener={provider:config.provider,model:config.model,protocol:config.protocol}
 const result={status:'failed',listener,agent_received_audio_directly:false,
  listening:{status:'not_performed'},inputs:[],observations:null}
 let secret=''
 try{
  if(config.protocol!=='gemini-generate-content')return {...result,status:'unsupported',reason_code:'unsupported_audio_protocol',
   next_action:'Configure an explicitly supported native audio route; changing a model name does not add audio support'}
  if(config.audioInput!==true) return {...result,status:'unsupported',reason_code:'audio_input_not_declared',
   next_action:'Use signal analysis or an administrator-validated audio-capable route'}
  if(typeof args.question!=='string'||!args.question.trim()||args.question.length>12000)throw Error('Provide a concise listening question')
  const primary=await artifact(ctx,exec,args.preview_manifest,args.artifact_id,config.maxAudioBytes??12_000_000)
  const clips=[primary]
  if(args.reference_manifest)clips.push(await artifact(ctx,exec,args.reference_manifest,args.reference_artifact_id,config.maxAudioBytes??12_000_000))
  result.inputs=clips.map(c=>c.input)
  const parts=[{text:'Evaluate the actual audio for a music-production agent. Distinguish audible observations, aesthetic preferences and uncertainty. Do not infer from filenames or claim a parameter mechanism is proven by listening. Give timestamps relative to each supplied clip. '+args.question}]
  for(const [index,clip] of clips.entries()){
   parts.push({text:`Clip ${index===0?'A':'B'}; supplied duration ${clip.input.duration_seconds.toFixed(3)} seconds.`})
   parts.push({inlineData:{mimeType:clip.input.mime_type,data:clip.bytes.toString('base64')}})
  }
  const body=JSON.stringify({contents:[{role:'user',parts}],generationConfig:{maxOutputTokens:config.maxOutputTokens??1800}})
  const requestBytes=Buffer.byteLength(body)
  if(requestBytes>(config.maxRequestBytes??18_000_000))return {...result,status:'unsupported',reason_code:'audio_request_too_large',
   next_action:'Create an MP3 listening copy with audio preview encoding=mp3, shorten the selected window, or evaluate the clips separately'}
  result.request={audio_parts:clips.length,request_bytes:requestBytes,payload_sha256:sha(body),
   audio_payload_attached:true}
  const credential=await ctx.credentials.resolve(config.credentialRef)
  secret=credential?.value??''
  if(!secret)throw Error(`Configured audio credential reference ${config.credentialRef} is unavailable`)
  const base=new URL(config.baseURL)
  if(base.protocol!=='https:')throw Error('Native audio route must use its configured HTTPS endpoint')
  const url=new URL(`${base.pathname.replace(/\/$/,'')}/v1beta/models/${encodeURIComponent(config.model)}:generateContent`,base.origin)
  const signal=AbortSignal.any([exec.signal,AbortSignal.timeout(config.timeoutMs??90000)].filter(Boolean))
  const started=Date.now()
  const response=await fetch(url,{method:'POST',headers:{'content-type':'application/json','x-goog-api-key':secret,
   authorization:`Bearer ${secret}`},body,signal})
  result.request.elapsed_seconds=(Date.now()-started)/1000
  result.request.http_status=response.status
  let data
  try{data=await response.json()}catch{throw Error(`Audio provider returned non-JSON content (${response.status})`)}
  if(!response.ok)throw Error(data.error?.message??`Audio provider returned HTTP${response.status}`)
  listener.request_id=data.responseId??response.headers.get('x-request-id')??null
  result.usage=data.usageMetadata??null
  const observations=(data.candidates??[]).flatMap(c=>c.content?.parts??[])
   .filter(p=>typeof p.text==='string'&&!p.thought).map(p=>p.text).join('\n').trim()
  if(!observations)throw Error('Audio provider returned no observations; listening remains unconfirmed')
  const finishReasons=(data.candidates??[]).map(c=>c.finishReason??'unknown')
  return {...result,status:'evaluated',observations,response_finish_reasons:finishReasons,
   observations_truncated:finishReasons.includes('MAX_TOKENS'),listening:{status:'performed',who:`${listener.provider} / ${listener.model}`,
   listener,
   method:'Native audio model input, not transcript or signal-metric substitution',
   scope:'Only the selected transmitted artifacts; subjective observations are not an objective quality ranking'}}
 }catch(error){
  const message=String(error?.message??error)
  return {...result,reason_code:exec.signal?.aborted?'listening_cancelled':'audio_evaluation_failed',
   error:(secret?message.split(secret).join('[redacted]'):message).slice(0,1500),
   next_action:'Inspect the named cause; keep the existing audio and use signal analysis while correcting the listener route'}
 }
}

export function apply(ctx,config){
 if(!config||typeof config.provider!=='string'||typeof config.model!=='string'||typeof config.credentialRef!=='string')throw Error('FL audio listener requires explicit provider/model/credentialRef configuration')
 ctx.tools.register({
  name:'listen_audio',
  description:'Listen to real FL Studio audio through the configured native audio model. Pass a ready CLI audio-preview, sound-design audition.json or new comparison.json; optionally compare a second manifest as clip B. The selected audio bytes are sent to that configured model. Returns attributed listening observations; the current conversation itself does not receive audio. Supply output_file to save an exact receipt directly for sound-design report --listening, avoiding retyping or wrapping JSON. Text-only agents can delegate listening with this tool.',
  parameters:{type:'object',additionalProperties:false,properties:{
   preview_manifest:{type:'string',description:'Absolute preview.json, audition.json or new comparison.json path.'},
   artifact_id:{type:'string',description:'Optional artifact id; default listening copy/audio, context-1 for auditions, or candidate:solo/context for comparisons.'},
   question:{type:'string',description:'The musical listening question; request timestamps and uncertainty.'},
   output_file:{type:'string',description:'Optional new absolute JSON receipt path in an existing directory. Existing files are preserved. Pass this file directly to sound-design report --listening when status=evaluated.'},
   reference_manifest:{type:'string',description:'Optional absolute manifest for a comparative clip B.'},
   reference_artifact_id:{type:'string'}},required:['preview_manifest','question']},
  output:{schema:{type:'object',additionalProperties:true},render:(_args,value)=>textResult(value)},
  timeoutMs:120000,
  isConcurrencySafe:()=>true,
  execute:async(args,exec)=>{
   let target,result
   try{
    if(args.output_file){
     if(!isAbsolute(args.output_file))throw Error('Listening receipt needs a new absolute output_file path')
     target=await ctx.fs.resolve(args.output_file,{signal:exec.signal})
     if(await ctx.fs.stat(target,exec.signal))throw Error('Listening output_file already exists; keep it or choose a new receipt path')
    }
    result=await evaluateAudio(ctx,config,args,exec)
    if(target){
     result.evidence_file=args.output_file
     await ctx.fs.writeText(target,JSON.stringify(result,null,2)+'\n',{kind:'createIfAbsent'},exec.signal)
    }
    return result
   }catch(error){
    return {...result,status:'failed',reason_code:'listening_receipt_failed',
     error:String(error?.message??error).slice(0,1000),
     next_action:'Choose a new writable receipt path; if listening already performed, retain the returned observations instead of repeating the model request'}
   }
  },
  presentCall:args=>({card:'generic',kind:args.output_file?'write':'read',title:'Listen to FL audio',locations:[{path:args.preview_manifest},...(args.output_file?[{path:args.output_file}]:[])]})
 })
}
