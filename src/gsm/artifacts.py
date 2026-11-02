"""Product-written immutable release files in the shared knowledge directory."""
import hashlib,json,os,tempfile,shutil,errno
from pathlib import Path
from .errors import ProductError


def dump(value):return json.dumps(value,ensure_ascii=False,indent=2)+'\n'


def atomic(path,text):
    path=Path(path)
    if path.is_symlink():raise ProductError('INVALID_ARTIFACT_PATH','发布元数据不能通过符号链接写入')
    fd,name=tempfile.mkstemp(prefix='.gsm-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as out:out.write(text);out.flush();os.fsync(out.fileno())
        os.replace(name,path)
    finally:
        if Path(name).exists():Path(name).unlink()


def prepare(root,release_id,manifest,records,domain):
    from .shared_runtime import registry
    root=Path(root).resolve();operator,_=registry(root);base=operator/'prepared-releases'
    base.mkdir(exist_ok=True);dest=base/release_id
    files={'semantic/records.json':dump({'records':records}),'semantic/graph.json':dump({'edges':[r for r in records if r['kind']=='relation']}),'domain.json':dump(domain),'wiki/catalog.json':dump(manifest['wiki'].get('catalog',[]))}
    for page in manifest['wiki'].get('pages',[]):
        name=page['path']
        if Path(name).name!=name or not name.endswith('.md'):raise ProductError('INVALID_WIKI_PATH','Wiki页面路径不合法')
        files['wiki/'+name]=page['text']
    public={**manifest,'release_id':release_id,'files':{name:hashlib.sha256(value.encode()).hexdigest() for name,value in files.items()}}
    if dest.exists():
        if dest.is_symlink() or json.loads((dest/'manifest.json').read_text())!=public:raise ProductError('ARTIFACT_CONFLICT','同一发布ID的现有文件不一致')
        for name,digest in public['files'].items():
            if hashlib.sha256((dest/name).read_bytes()).hexdigest()!=digest:raise ProductError('ARTIFACT_CONFLICT','已导出发布文件发生变化')
        return
    with tempfile.TemporaryDirectory(prefix='.preparing-',dir=base) as temporary:
        stage=Path(temporary)
        for name,value in files.items():
            file=stage/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(value)
        (stage/'manifest.json').write_text(dump(public))
        os.rename(stage,dest)


def expose(root,release_id):
    from .shared_runtime import registry
    root=Path(root).resolve();operator,_=registry(root);base=root/'releases';target=base/release_id;prepared=operator/'prepared-releases'/release_id
    if base.is_symlink() or not base.resolve().is_relative_to(root):raise ProductError('INVALID_ARTIFACT_PATH','发布目录必须位于知识库内')
    if target.is_symlink():raise ProductError('INVALID_ARTIFACT_PATH','发布文件夹不接受符号链接')
    if not target.exists() and prepared.is_dir():
        try:os.rename(prepared,target)
        except OSError as error:
            if error.errno!=errno.EXDEV:raise
            with tempfile.TemporaryDirectory(prefix='.exporting-',dir=base) as tmp:
                stage=Path(tmp)/'release';shutil.copytree(prepared,stage);os.rename(stage,target)
    if not target.is_dir():raise ProductError('EXPORT_NOT_READY','发布文件尚未就绪，可重试同一发布')


def current(root,release_id):
    root=Path(root).resolve();expose(root,release_id)
    # Database authority is read while the product publication lock is held.
    atomic(root/'CURRENT.json',dump({'release_id':release_id,'manifest':'releases/'+release_id+'/manifest.json','authority':'fixed release ID; MCP validates current authorization'}))
    wiki=root/'wiki'
    if wiki.is_dir() and not wiki.is_symlink():
        if any(wiki.iterdir()):raise ProductError('ARTIFACT_CONFLICT','Wiki目录含未登记文件，拒绝覆盖')
        wiki.rmdir()
    name=root/('.wiki-'+release_id)
    if name.exists() or name.is_symlink():name.unlink()
    name.symlink_to(Path('releases')/release_id/'wiki',target_is_directory=True);os.replace(name,wiki)

    metadata=root/'KNOWLEDGE_BASE.json'
    if metadata.exists():
        info=json.loads(metadata.read_text());info.update(status='published',current_release=release_id)
        atomic(metadata,dump(info))
