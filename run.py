#!/usr/bin/env python3
"""Frozen live experiment. Credentials enter only through OPENAI_API_KEY."""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import unicodedata
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
HEADERS = {'date','content-type','x-request-id','openai-model','openai-version','openai-processing-ms'}

def utc():
    return datetime.now(timezone.utc).isoformat()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def json_bytes(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')

def exclusive(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())

def expected_trials(protocol):
    trials=[]
    for replicate in range(1,protocol['repetitions']+1):
        for pair in protocol['pairs']:
            for role in ('null','control'):
                models=protocol['models'] if replicate%2 else protocol['models'][::-1]
                for model in models:
                    trials.append({'trial_id':f't{len(trials)+1:03d}',
                                   'requested_model':model,'pair_id':pair['pair_id'],
                                   'role':role,'replicate':replicate,'user_prompt':pair[role]})
    return trials

def request_for(trial, protocol):
    return {'model':trial['requested_model'],
            'messages':[{'role':'system','content':protocol['system_prompt']},
                        {'role':'user','content':trial['user_prompt']}],
            **protocol['settings']}

def classify_response(raw, http_status, expected_model, transport_error=None,
                      raw_response_received=True):
    out={'classification':'OP','returned_model':None,'response_id':None,'usage':None,
         'message_content':None,'text_container_present':False,'visible_utf8_bytes':None,
         'visible_sha256':None,'finish_reason':None,'refusal':None,'tool_calls':None,
         'function_call':None}
    try:
        body=json.loads(raw.decode('utf-8'))
    except (ValueError,UnicodeError):
        return out
    if not isinstance(body,dict):
        return out
    out.update(returned_model=body.get('model'),response_id=body.get('id'),usage=body.get('usage'))
    choices=body.get('choices')
    if not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0],dict):
        return out
    choice=choices[0]; message=choice.get('message')
    out['finish_reason']=choice.get('finish_reason')
    if not isinstance(message,dict):
        return out
    content=message.get('content')
    out.update(message_content=content,text_container_present=isinstance(content,str),
               refusal=message.get('refusal'),tool_calls=message.get('tool_calls'),
               function_call=message.get('function_call'))
    if isinstance(content,str):
        try:
            visible=content.encode('utf-8')
        except UnicodeError:
            return out
        out.update(visible_utf8_bytes=len(visible),visible_sha256=digest(visible))
    elif content is None:
        out.update(visible_utf8_bytes=0,visible_sha256=digest(b''))
    if (transport_error is not None or not raw_response_received or
        not isinstance(http_status,int) or not 200<=http_status<300 or
        body.get('error') is not None or body.get('model')!=expected_model or
        message.get('role')!='assistant'):
        return out
    stop=out['finish_reason']
    if out['refusal'] or stop=='refusal':
        out['classification']='RF'
    elif stop=='content_filter':
        out['classification']='SB'
    elif out['tool_calls'] or out['function_call'] or stop in ('tool_calls','function_call'):
        out['classification']='TC'
    elif content is not None and not isinstance(content,str):
        out['classification']='OP'
    elif content:
        near=all(c.isspace() or unicodedata.category(c).startswith('P') or
                 unicodedata.category(c) in ('Cf','Cc') for c in content)
        out['classification']='NV' if near else 'R'
    elif stop=='stop' and out['text_container_present']:
        out['classification']='V0'
    elif stop=='length':
        out['classification']='V1'
    else:
        out['classification']='VU'
    return out

class Events:
    def __init__(self,path):
        self.stream=path.open('xb'); self.seq=0; self.previous=None

    def add(self,event_type,**fields):
        self.seq+=1
        event={'type':event_type,'timestamp_utc':utc(),'seq':self.seq,
               'previous_sha256':self.previous,**fields}
        line=(json.dumps(event,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')
        self.stream.write(line); self.stream.flush(); os.fsync(self.stream.fileno())
        self.previous=digest(line)

    def close(self):
        self.stream.close()

def source_files(root):
    names=['protocol.json','PROTOCOL.md','run.py','verify.py','analyze.py',
           'run.sh','verify.sh','.gitignore']
    names += [str(p.relative_to(root)) for p in sorted((root/'tests').rglob('*'))
              if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    return names

def freeze(root):
    if (root/'FREEZE.json').exists() or (root/'events.jsonl').exists():
        raise RuntimeError('Existing freeze or run; use a fresh directory.')
    names=source_files(root)
    if not any(n.startswith('tests/') for n in names):
        raise RuntimeError('Offline tests must exist before freezing.')
    record={'schema_version':1,'frozen_at_utc':utc(),
            'sha256':{name:digest((root/name).read_bytes()) for name in names}}
    exclusive(root/'FREEZE.json',json_bytes(record))
    print(json.dumps({'status':'FROZEN','protocol_sha256':record['sha256']['protocol.json']}))

def execute(root):
    from verify import verify_freeze
    protocol=verify_freeze(root)
    if protocol['endpoint']!='https://api.openai.com/v1/chat/completions':
        raise RuntimeError('Unexpected endpoint.')
    if (root/'records').exists() or (root/'events.jsonl').exists() or (root/'results').exists():
        raise RuntimeError('Existing run artifacts; no overwrite or implicit resume.')
    key=os.environ.get('OPENAI_API_KEY')
    if not key or not key.startswith('sk-') or any(c.isspace() for c in key):
        raise RuntimeError('Set a valid OPENAI_API_KEY environment variable.')
    trials=expected_trials(protocol)
    if len(trials)!=protocol['total_scheduled_calls']:
        raise RuntimeError('Schedule size mismatch.')
    commit=(root/'FREEZE_COMMIT.txt').read_text().strip()
    events=Events(root/'events.jsonl')
    try:
        events.add('run_started',freeze_commit=commit,
                   protocol_sha256=digest((root/'protocol.json').read_bytes()),
                   scheduled_trials=len(trials))
        for trial in trials:
            trial_id=trial['trial_id']; stem=trial_id+'.attempt-1'
            request_path='records/requests/'+stem+'.json'
            raw_path='records/raw/'+stem+'.body'
            header_path='records/raw/'+stem+'.headers.json'
            record_path='records/raw/'+stem+'.record.json'
            request_raw=json.dumps(request_for(trial,protocol),ensure_ascii=False,
                                   separators=(',',':')).encode('utf-8')
            exclusive(root/request_path,request_raw)
            events.add('trial_started',trial_id=trial_id,attempt_number=1,
                       request_path=request_path,request_sha256=digest(request_raw))
            started=utc(); status=None; raw=b''; headers=[]; transport_error=None
            response_received=False; body_complete=False
            conn=http.client.HTTPSConnection('api.openai.com',timeout=protocol['timeout_seconds'])
            try:
                conn.request('POST','/v1/chat/completions',body=request_raw,
                             headers={'Authorization':'Bearer '+key,
                                      'Content-Type':'application/json','Accept':'application/json'})
                response=conn.getresponse(); response_received=True; status=response.status
                headers=[[k,v] for k,v in response.getheaders() if k.lower() in HEADERS]
                try:
                    raw=response.read(); body_complete=True
                except http.client.IncompleteRead as error:
                    raw=error.partial; transport_error='IncompleteRead'
            except (OSError,http.client.HTTPException) as error:
                transport_error=type(error).__name__
            finally:
                conn.close()
            ended=utc(); header_raw=json_bytes(headers)
            exclusive(root/raw_path,raw); exclusive(root/header_path,header_raw)
            extracted=classify_response(raw,status,trial['requested_model'],transport_error,response_received)
            record={'schema_version':1,**trial,'attempt_number':1,
                    'system_prompt':protocol['system_prompt'],**protocol['settings'],
                    'started_at_utc':started,'ended_at_utc':ended,'http_status':status,
                    'transport_error':transport_error,'raw_response_received':response_received,
                    'response_body_complete':body_complete,
                    'request_path':request_path,'request_sha256':digest(request_raw),
                    'raw_response_path':raw_path,'raw_response_sha256':digest(raw),
                    'headers_path':header_path,'headers_sha256':digest(header_raw),
                    'unicode_version':unicodedata.unidata_version,**extracted}
            record_raw=json_bytes(record); exclusive(root/record_path,record_raw)
            events.add('trial_finished',trial_id=trial_id,attempt_number=1,
                       record_path=record_path,record_sha256=digest(record_raw),
                       raw_response_path=raw_path,raw_response_sha256=digest(raw),
                       headers_path=header_path,headers_sha256=digest(header_raw),
                       classification=record['classification'])
            print(json.dumps({'trial_id':trial_id,'model':trial['requested_model'],
                              'http_status':status,'classification':record['classification'],
                              'visible_utf8_bytes':record['visible_utf8_bytes']}),flush=True)
        events.add('run_finished',completed_trials=len(trials))
    finally:
        events.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',action='store_true',help='Hash source/protocol before a new freeze commit.')
    args=parser.parse_args()
    if args.freeze:
        freeze(ROOT)
    else:
        execute(ROOT)

if __name__=='__main__':
    main()
