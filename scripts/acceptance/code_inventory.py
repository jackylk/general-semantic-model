"""Current C1 repository code size; generated artifacts and external dependencies excluded."""
import json,re,subprocess,hashlib
from pathlib import Path
r=Path(Path('runtime/acceptance-root.txt').read_text());c=r/'control';groups={}
for name,folder,pattern in [('product_python','src','*.py'),('tests_python','tests','*.py'),('scripts_python','scripts','*.py'),('workspace_launcher','templates','*.py'),('migrations_sql','migrations','*.sql')]:
    files=sorted(Path(folder).rglob(pattern));counts=[]
    for p in files:
        lines=p.read_text().splitlines();counts.append({'file':str(p),'lines':len(lines),'nonblank':sum(bool(x.strip()) for x in lines),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    groups[name]={'files':len(counts),'lines':sum(x['lines'] for x in counts),'nonblank':sum(x['nonblank'] for x in counts),'details':counts}
tables=[]
for p in sorted(Path('migrations').glob('*.sql')):tables+=re.findall(r'CREATE TABLE\s+(?:IF NOT EXISTS\s+)?([a-z_]+)',p.read_text(),re.I)
paths=['src','tests','scripts','templates','migrations'];numstat=subprocess.check_output(['git','diff','--numstat','5c26661','--',*paths],text=True)
report={'method':'Current physical/nonblank lines, not keystrokes or logical LOC. Product, tests and automation separated. No models, wheels, external MinerU or C2 domain assets counted. git numstat excludes currently untracked files; current file inventory includes them.','git_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'groups':groups,'predefined_physical_tables':tables,'predefined_physical_table_count':len(tables),'generic_record_kinds':['object','assertion','relation','event','rule'],'predefined_automotive_tables':0,'predefined_automotive_graphs':0,'graph_implementation':'Version-pinned relation records projected into directed edges and queried by recursive SQL; no prebuilt industry graph.','git_numstat_since_design_baseline':numstat}
(c/'code-inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print({k:{x:y for x,y in v.items() if x!='details'} for k,v in groups.items()});print('fixed tables',len(tables),tables)
