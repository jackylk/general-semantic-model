"""Archive an explicit allowlist; never copy Codex auth homes or role secrets."""
import json,shutil,hashlib
from pathlib import Path
from dotenv import dotenv_values
root=Path.cwd();r=Path((root/'runtime/acceptance-root.txt').read_text());c=r/'control'
out=r/'artifacts/2026-11-02-three-codex';out.mkdir(parents=True,exist_ok=True)
control_names=['latest-release-audit.json','final-results.json','environment.json','run.json','gold.json','questions.json','boundary-results.json','worker-restart-probe.json','embedding-bounded-stress.json','answer-evidence-audit.json','answer-evidence-reads.json','role-trace-audit.json','lifecycle-audit.json','developer.sb','consumer.sb']
files=[(c/name,Path('control')/name) for name in control_names if (c/name).is_file()]
files +=[(p,Path('control')/p.name) for pattern in ['*-phase*.jsonl','*-phase*.stderr','*-phase*-prompt.txt','*-mcp.jsonl','*-server.log','worker.log'] for p in c.glob(pattern)]
files +=[(p,Path('reference')/p.name) for p in (c/'reference').iterdir() if p.is_file()]
for role in ['developer','consumer']:
 for p in (r/role).rglob('*'):
  rel=p.relative_to(r/role)
  if p.is_file() and not any(x in ('.codex','documents','tmp') for x in rel.parts) and p.suffix in ('.json','.yaml','.md') and p.name!='credentials.json':files.append((p,Path(role)/rel))
secrets=[(c/f'{role}.token').read_text().strip().encode() for role in ['developer','consumer']]
key=dotenv_values(Path.home()/'code/.env').get('DEEPSEEK_API_KEY');sign=dotenv_values(root/'.env').get('GSM_CREDENTIAL_SIGNING_KEY')
secrets +=[v.encode() for v in [key,sign] if v]
manifest=[]
for source,rel in files:
 data=source.read_bytes()
 if any(s and s in data for s in secrets):raise SystemExit(f'secret scan rejected {rel}')
 dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);manifest.append({'path':str(rel),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
(out/'MANIFEST.json').write_text(json.dumps({'secret_scan':'passed: exact role tokens, API key and signing key absent','excluded':'auth homes, auth.json, tokens, credentials, document PDFs, temp files','files':manifest},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'archive':str(out),'files':len(manifest),'bytes':sum(x['bytes'] for x in manifest),'secret_scan':'passed'}))
