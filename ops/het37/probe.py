#!/usr/bin/env python3
"""Authenticated missing-provider HTTP/UI proof; no provider or social operation."""
import argparse,json,pathlib,time,urllib.request,urllib.error
p=argparse.ArgumentParser();p.add_argument('--origin',default='https://socials.qwntik.com');p.add_argument('--cookie-file',type=pathlib.Path,default=pathlib.Path('/opt/qwntik-postiz/bootstrap-cookie.txt'));a=p.parse_args();cookie=a.cookie_file.read_text().split(';',1)[0];results=[]
for path in ['/api/copilot/chat','/api/copilot/agent']:
 start=time.monotonic();r=urllib.request.Request(a.origin+path,data=json.dumps({'method':'info'}).encode(),headers={'Cookie':cookie,'Content-Type':'application/json','User-Agent':'Qwntik-Postiz-Ops/1.0'})
 try:
  with urllib.request.urlopen(r,timeout=3)as v:status=v.status;body=json.load(v)
 except urllib.error.HTTPError as e:status=e.code;body=json.loads(e.read())
 elapsed=time.monotonic()-start;assert status==503 and body['code']=='AI_PROVIDER_NOT_CONFIGURED'and elapsed<1.5,(path,status,elapsed);results.append({'route':path,'status':status,'seconds':round(elapsed,3),'clearUnconfiguredMessage':True})
r=urllib.request.Request(a.origin+'/agents/new',headers={'Cookie':cookie,'User-Agent':'Qwntik-Postiz-Ops/1.0'})
with urllib.request.urlopen(r,timeout=5)as v:body=v.read().decode();assert v.status==200 and 'Built-in AI is not configured on this server.'in body
print(json.dumps({'copilot':results,'agentPageClearStatus':True,'scope':'runtime info and SSR only; no model/tool/social/email operation'},indent=2))
