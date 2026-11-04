#!/usr/bin/env python3
"""Isolated unchanged-image boot against dry restores; no public ports/providers."""
import json,pathlib,subprocess,time,yaml
P=pathlib.Path('/opt/qwntik-postiz/het35')
def run(a):
 r=subprocess.run(a,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if r.returncode:raise RuntimeError(a[0]+' failed '+r.stderr.decode()[-1000:])
 return r.stdout.decode()
def image(n):return json.loads(run(['docker','inspect',n]))[0]['Image']
net='qwntik-postiz-het35-isolated'
if subprocess.run(['docker','network','inspect',net],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:run(['docker','network','create','--internal',net])
for n in ['postiz-central-db-1','postiz-temporal-db-1']:
 networks=json.loads(run(['docker','inspect',n]))[0]['NetworkSettings']['Networks']
 if net not in networks:run(['docker','network','connect',net,n])
e={'MAIN_URL':'http://het35-app','FRONTEND_URL':'http://het35-app','NEXT_PUBLIC_BACKEND_URL':'http://het35-app/api','JWT_SECRET':'isolated-fixture-only-not-production','DATABASE_URL':'postgresql://postiz_app:'+ (P/'app-password.txt').read_text().strip()+'@postiz-central-db-1:57322/postgres','REDIS_URL':'redis://het35-redis:6379','BACKEND_INTERNAL_URL':'http://localhost:3000','TEMPORAL_ADDRESS':'het35-temporal:7233','IS_GENERAL':'true','DISABLE_REGISTRATION':'true','RUN_CRON':'false','STORAGE_PROVIDER':'local','UPLOAD_DIRECTORY':'/uploads','NEXT_PUBLIC_UPLOAD_DIRECTORY':'/uploads','NX_ADD_PLUGINS':'false','EMAIL_PROVIDER':'resend','EMAIL_FROM_ADDRESS':'fixture@example.invalid','EMAIL_FROM_NAME':'Isolated fixture'}
t={'DB':'postgres12','DB_PORT':'58322','POSTGRES_USER':'postiz_temporal','POSTGRES_PWD':(P/'temporal/app-password.txt').read_text().strip(),'POSTGRES_SEEDS':'postiz-temporal-db-1','DBNAME':'postgres','ENABLE_ES':'true','ES_SEEDS':'het35-es','ES_VERSION':'v7','TEMPORAL_NAMESPACE':'default','SKIP_SCHEMA_SETUP':'true','SKIP_DB_CREATE':'true','SKIP_DEFAULT_NAMESPACE_CREATION':'true','SKIP_ADD_CUSTOM_SEARCH_ATTRIBUTES':'true'}
c={'name':'qwntik-postiz-het35-rehearsal','services':{
 'es':{'container_name':'het35-es','image':image('qwntik-postiz-temporal-elasticsearch'),'environment':{'discovery.type':'single-node','ES_JAVA_OPTS':'-Xms256m -Xmx256m','xpack.security.enabled':'false'},'networks':['isolated']},
 'redis':{'container_name':'het35-redis','image':image('qwntik-postiz-postiz-redis'),'networks':['isolated']},
 'temporal':{'container_name':'het35-temporal','image':image('qwntik-postiz-temporal'),'environment':t,'networks':['isolated']},
 'app':{'container_name':'het35-app','image':image('qwntik-postiz-postiz'),'environment':e,'networks':['isolated'],'volumes':['fixture-uploads:/uploads','fixture-config:/config']}
 },'networks':{'isolated':{'external':True,'name':net}},'volumes':{'fixture-uploads':{},'fixture-config':{}}}
f=P/'rehearsal.yaml';f.write_text(yaml.safe_dump(c,sort_keys=False));f.chmod(0o600)
run(['docker','compose','-f',str(f),'up','-d','es','redis'])
for _ in range(60):
 r=subprocess.run(['docker','exec','het35-es','curl','-fsS','http://127.0.0.1:9200/_cluster/health'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 if r.returncode==0:break
 time.sleep(1)
else:raise RuntimeError('fixture ES not ready')
run(['docker','compose','-f',str(f),'up','-d','temporal'])
for _ in range(60):
 r=subprocess.run(['docker','exec','het35-temporal','temporal','operator','cluster','health','--address','het35-temporal:7233'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 if r.returncode==0:break
 time.sleep(1)
else:raise RuntimeError('fixture Temporal not ready')
run(['docker','compose','-f',str(f),'up','-d','app'])
for _ in range(90):
 r=subprocess.run(['docker','exec','het35-app','node','-e',"fetch('http://127.0.0.1:5000/auth/login',{redirect:'manual'}).then(r=>process.exit(r.status===200?0:1)).catch(()=>process.exit(1))"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 if r.returncode==0:break
 time.sleep(1)
else:raise RuntimeError('fixture app not ready')
probe="""const {PrismaClient}=require('@prisma/client');const p=new PrismaClient();(async()=>{try {await p.$transaction(async tx=>{await tx.$executeRawUnsafe('CREATE TABLE public.het35_isolated_probe(id integer PRIMARY KEY)');await tx.$executeRawUnsafe('INSERT INTO public.het35_isolated_probe VALUES(1)');const r=await tx.$queryRawUnsafe('SELECT count(*)::int AS n FROM public.het35_isolated_probe');if(r[0].n!==1)throw Error('probe count');throw Error('rollback-probe')})}catch(e){if(!e.message.includes('rollback-probe'))throw e}const r=await p.$queryRawUnsafe("SELECT to_regclass('public.het35_isolated_probe') IS NULL AS clean");if(!r[0].clean)throw Error('probe leaked');await p.$disconnect()})().catch(()=>process.exit(1));"""
run(['docker','exec','-w','/app','het35-app','node','-e',probe])
pm=json.loads(run(['docker','exec','het35-app','pm2','jlist']))
assert len(pm)==3 and all(x['pm2_env']['status']=='online' for x in pm)
# Isolated environment has no provider credentials or ports and no route to live networks.
for n in ['het35-app','het35-temporal','het35-es','het35-redis']:
 d=json.loads(run(['docker','inspect',n]))[0]
 assert list(d['NetworkSettings']['Networks'])==[net]
 assert not d['HostConfig']['PortBindings']
result={'image':image('het35-app'),'temporal_image':image('het35-temporal'),'app_pm2':3,'temporal_pg17_health':'SERVING','network_internal':True,'published_ports':0,'external_provider_credentials':False}
(P/'rehearsal-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
print('isolated exact-image app3PM2 and TemporalPG17 health PASS; no public ports/providers')
