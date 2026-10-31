"""Reproduce the isolated local native-text MinerU runtime without editing its source."""
import argparse,subprocess
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=Path);p.add_argument('--wheelhouse',type=Path);p.add_argument('--index-url',default='https://pypi.org/simple');a=p.parse_args()
    root=Path(__file__).resolve().parents[1];source=a.source.resolve();env=root/'runtime/mineru'
    expected='0ef2c20c4a56e68f81a66647f819d924ef2d89ce'
    actual=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if actual!=expected:raise SystemExit('MinerU source commit differs from validated version; review adapter compatibility first')
    if not (env/'bin/python').exists():subprocess.run(['uv','venv',str(env),'--python','3.12','--seed'],check=True)
    args=[str(env/'bin/python'),'-m','pip','install','-r',str(root/'requirements-mineru-flash.lock')]
    args+=['--no-index','--find-links',str(a.wheelhouse.resolve())] if a.wheelhouse else ['--index-url',a.index_url]
    subprocess.run(args,check=True)
    site=subprocess.check_output([str(env/'bin/python'),'-c','import site;print(site.getsitepackages()[0])'],text=True).strip()
    (Path(site)/'local-mineru.pth').write_text(str(source)+'\n')
    script=env/'bin/mineru-kit';script.write_text(f'#!{env}/bin/python\nfrom mineru.kit.main import main\nif __name__ == "__main__":\n    main()\n');script.chmod(0o755)
    print('Local native-text MinerU runtime ready. OCR weights/backends are not covered by this setup.')

if __name__=='__main__':main()
