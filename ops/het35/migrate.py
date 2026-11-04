#!/usr/bin/env python3
"""HET-35 reviewed staged migration; no implicit production cutover."""
import argparse, hashlib, json, os, pathlib, secrets, subprocess
P=pathlib.Path('/opt/qwntik-postiz/het35'); P.mkdir(mode=0o700,exist_ok=True)
SRC='qwntik-postiz-postiz-postgres'; DST='postiz-central-db-1'; PORT='57322'
def run(args,data=None):
 r=subprocess.run(args,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if r.returncode: raise RuntimeError('command failed: '+args[0]+' '+r.stderr.decode()[-1800:])
 return r.stdout
def sql(c,q):
 args=['docker','exec','-i',c,'psql','-X','-v','ON_ERROR_STOP=1','-At','-U','postiz-user' if c==SRC else 'postgres','-d','postiz-db-local' if c==SRC else 'postgres']
 if c==DST: args+=['-p',PORT]
 return run(args,q.encode()).decode().strip()
def fingerprint(c):
 names=sql(c,"SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;").splitlines(); tables={}
 queries=[]
 for n in names:
  q='"'+n.replace('"','""')+'"'
  literal="'"+n.replace("'","''")+"'"
  queries.append(f"SELECT {literal}, count(*) || ':' || md5(COALESCE(string_agg(h,',' ORDER BY h),'')) FROM (SELECT md5(row_to_json(t)::text) h FROM public.{q} t) s")
 if queries:
  tables=dict(x.split('|',1) for x in sql(c,' UNION ALL '.join(queries)+';').splitlines())

 seq=sql(c,"SELECT sequencename,start_value,min_value,max_value,increment_by,cycle,last_value FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename;")
 cols=sql(c,"SELECT table_name,column_name,row_number() OVER (PARTITION BY table_name ORDER BY ordinal_position),data_type,udt_name,is_nullable,coalesce(column_default,'') FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position;")
 catalog=sql(c,"""SELECT 'index',indexname,indexdef FROM pg_indexes WHERE schemaname='public'
 UNION ALL SELECT 'constraint',c.conname,pg_get_constraintdef(c.oid) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='public'
 UNION ALL SELECT 'enum',t.typname,string_agg(e.enumlabel,',' ORDER BY e.enumsortorder) FROM pg_type t JOIN pg_enum e ON e.enumtypid=t.oid JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public' GROUP BY t.typname
 UNION ALL SELECT 'trigger',t.tgname,pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND NOT t.tgisinternal
 UNION ALL SELECT 'function',p.proname,pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.prokind IN ('f','p')
 UNION ALL SELECT 'policy',tablename||':'||policyname,coalesce(qual,'')||':'||coalesce(with_check,'') FROM pg_policies WHERE schemaname='public'
 ORDER BY 1,2,3;""")
 return {'catalog_sha256':hashlib.sha256(catalog.encode()).hexdigest(),'tables':tables,'sequences':seq,'columns_sha256':hashlib.sha256(cols.encode()).hexdigest()}
def dump(label):
 f=P/(label+'.dump'); f.write_bytes(run(['docker','exec',SRC,'pg_dump','-U','postiz-user','-d','postiz-db-local','-Fc','-n','public'])); f.chmod(0o600)
 (P/(label+'-source.json')).write_text(json.dumps(fingerprint(SRC),indent=2)+'\n')
 return f
ap=argparse.ArgumentParser(); ap.add_argument('phase',choices=['inventory','initialize','dry-restore','final-restore','compare']); a=ap.parse_args()
if a.phase=='inventory':
 for c in [SRC,DST]:
  result={'version':sql(c,'SELECT version();'),'extensions':sql(c,'SELECT extname,extversion,extnamespace::regnamespace FROM pg_extension ORDER BY extname;'),'public':sql(c,"SELECT c.relname,c.relkind,pg_get_userbyid(c.relowner) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY 1;"),'fingerprint':fingerprint(c)}
  (P/(c+'-baseline.json')).write_text(json.dumps(result,indent=2)+'\n')
 print('baseline inventories saved; no row data output')
elif a.phase=='initialize':
 assert sql(DST,"SELECT count(*) FROM pg_tables WHERE schemaname='public';")=='0','target public is not empty'
 pwd=secrets.token_urlsafe(40); (P/'app-password.txt').write_text(pwd); (P/'app-password.txt').chmod(0o600)
 sql(DST,"CREATE ROLE postiz_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '"+pwd+"'; GRANT postiz_app TO postgres; REVOKE CREATE ON SCHEMA public FROM PUBLIC,anon,authenticated,service_role; GRANT USAGE,CREATE ON SCHEMA public TO postiz_app; GRANT CONNECT ON DATABASE postgres TO postiz_app; ALTER DEFAULT PRIVILEGES FOR ROLE postiz_app IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC,anon,authenticated,service_role; ALTER DEFAULT PRIVILEGES FOR ROLE postiz_app IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC,anon,authenticated,service_role; ALTER DEFAULT PRIVILEGES FOR ROLE postiz_app IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM PUBLIC,anon,authenticated,service_role;")
 print('scoped role initialized; credential protected')
elif a.phase in ['dry-restore','final-restore']:
 label='dry' if a.phase=='dry-restore' else 'final'
 if label=='final':
  state=run(['docker','inspect',SRC,'--format','{{.State.Running}}']).decode().strip(); assert state=='true'
  assert run(['docker','inspect','qwntik-postiz-postiz','--format','{{.State.Running}}']).decode().strip()=='false','stop all app writers first'
  assert sql(DST,"SELECT count(*) FROM pg_stat_activity WHERE usename='postiz_app' AND pid<>pg_backend_pid() AND backend_type='client backend';")=='0','target rehearsal writers still connected'
  assert sql(SRC,"SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND backend_type='client backend';")=='0','source still has sessions'
 (P/(label+'-pass.json')).unlink(missing_ok=True)
 f=dump(label)
 sql(DST,'DROP OWNED BY postiz_app; ALTER DEFAULT PRIVILEGES FOR ROLE postiz_app REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC; ALTER DEFAULT PRIVILEGES FOR ROLE postiz_app IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC,anon,authenticated,service_role; ALTER DEFAULT PRIVILEGES FOR ROLE postiz_app IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC,anon,authenticated,service_role; GRANT USAGE,CREATE ON SCHEMA public TO postiz_app; GRANT CONNECT ON DATABASE postgres TO postiz_app;')
 # pg_restore TOC excludes only existing SCHEMApublic; retain exact application objects.
 toc=run(['docker','exec','-i',DST,'pg_restore','-l'],f.read_bytes()).decode()
 toc='\n'.join(x for x in toc.splitlines() if not (' SCHEMA - public ' in x or ' COMMENT - SCHEMA public ' in x))+'\n'
 (P/(label+'-restore.list')).write_text(toc)
 run(['docker','cp',str(f),DST+':/tmp/het35.dump']); run(['docker','cp',str(P/(label+'-restore.list')),DST+':/tmp/het35.list'])
 run(['docker','exec',DST,'pg_restore','-U','postgres','-p',PORT,'-d','postgres','--exit-on-error','--single-transaction','--no-owner','--no-acl','--role=postiz_app','-L','/tmp/het35.list','/tmp/het35.dump'])
 sql(DST,'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC,anon,authenticated,service_role; REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC,anon,authenticated,service_role; REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC,anon,authenticated,service_role;')
 expected=json.loads((P/(label+'-source.json')).read_text()); actual=fingerprint(DST)
 (P/(label+'-target.json')).write_text(json.dumps(actual,indent=2)+'\n'); assert expected==actual,'restore fingerprint mismatch'
 assert sql(DST,"SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tableowner<>'postiz_app';")=='0'
 assert sql(DST,"SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN (VALUES ('anon'),('authenticated'),('service_role')) r(role) WHERE n.nspname='public' AND c.relkind IN ('r','p') AND has_table_privilege(r.role,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER');")=='0','API role table access'
 assert sql(DST,"SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname='postiz_app';")=='f'
 assert sql(DST,"SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(c.relacl) a WHERE n.nspname='public' AND a.grantee=0;")=='0','PUBLIC relation ACL'
 assert sql(DST,"SELECT has_schema_privilege('postiz_app','extensions','CREATE') OR has_database_privilege('postiz_app','postgres','CREATE');")=='f','extension admin privilege'
 (P/(label+'-pass.json')).write_text(json.dumps({'dump_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'source':expected,'target':actual},indent=2)+'\n')
 print(label,'restore PASS; exact89table hashes/schema/sequences and scoped role negative checks')
else:
 assert fingerprint(SRC)==fingerprint(DST); print('current source/target fingerprints match')
