"""C1-only source audit/reference extraction; never supplies domain assets to C2."""
import csv,json,hashlib
from pathlib import Path
from gsm.adapters.mineru import Parser

root=Path(Path('runtime/acceptance-root.txt').read_text());control=root/'control';out=control/'reference';out.mkdir(exist_ok=True)
rows=list(csv.DictReader(open('../automotive_data/catalog/documents.csv',encoding='utf-8-sig')))
titles=['beg_flexible_control_unit_onepager_en.pdf','ps_summary_electric-drive_en_rgb_150dpi_20210520.pdf','BMS物料清单_SLURB87.pdf','汽车高压BMS参考设计_TIDUF92.pdf','EH7-Maintenance Manua-EN.pdf','EHS7-Maintenance Manua-EN.pdf']
parser=Parser(command=str(Path('runtime/mineru/bin/mineru-kit').resolve()),timeout=300);manifest=[]
for i,title in enumerate(titles,1):
 row=next(r for r in rows if r['title']==title and r['status']=='downloaded');path=Path('../automotive_data')/row['path']
 parsed=parser.parse(path);name=f'doc{i:02d}'
 (out/f'{name}.json').write_text(json.dumps({'blocks':parsed.blocks,'raw':parsed.raw},ensure_ascii=False))
 (out/f'{name}.txt').write_text('\n\n'.join(f"[page {b.get('page')} block {b.get('block_index')}] {b['text']}" for b in parsed.blocks))
 entry={'id':name,'title':title,'path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'category':row['effective_category'],'pages':len(parsed.raw.get('pages',[])),'characters':sum(len(b['text']) for b in parsed.blocks),'market':row['market'],'scope':row['scope']}
 manifest.append(entry);print({k:entry[k] for k in ('id','title','pages','characters')},flush=True)
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
