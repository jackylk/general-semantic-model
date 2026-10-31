"""Read-only audit of a supplied CSV source catalog. No source mutations."""
import argparse,csv,hashlib,json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    rows=list(csv.DictReader((args.root/'catalog/documents.csv').open(encoding='utf-8-sig')))
    downloaded=[r for r in rows if r['status']=='downloaded'];errors=[]
    for row in downloaded:
        path=args.root/row['path']
        if not path.is_file():errors.append({'path':row['path'],'error':'missing'});continue
        digest=hashlib.sha256()
        with path.open('rb') as source:
            for block in iter(lambda:source.read(1024*1024),b''):digest.update(block)
        if path.stat().st_size!=int(row['bytes']) or digest.hexdigest()!=row['sha256']:
            errors.append({'path':row['path'],'error':'size_or_hash_mismatch'})
    report={'catalog_downloaded':len(downloaded),'sha256_checked':len(downloaded),'errors':errors,'scope':'file integrity only; not applicability, parse or coverage acceptance'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
