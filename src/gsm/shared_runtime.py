"""Operator-managed services for two roles sharing one KB directory."""
import fcntl,hashlib,json,os,secrets,shutil,signal,socket,subprocess,sys,time
from pathlib import Path
from urllib.request import Request,urlopen,build_opener,ProxyHandler
from urllib.error import HTTPError,URLError
from .config import Settings
from .errors import ProductError


def registry(root):
    root=Path(root).resolve();settings=Settings.load()
    pointer=settings.file_root.parent/'workspaces'/hashlib.sha256(str(root).encode()).hexdigest()
    try:
        operator=Path(pointer.read_text());info=json.loads((operator/'workspace.json').read_text())
    except (OSError,ValueError):raise ProductError('WORKSPACE_NOT_INITIALIZED','请先用产品init-kb初始化该目录') from None
    if info['workspace']!=str(root):raise ProductError('INVALID_WORKSPACE','知识库注册目录不匹配')
    return operator,info


def role_policy(root,role):
    if role not in ('producer','consumer'):raise ProductError('INVALID_ROLE','未知客户端角色')
    root=Path(root).resolve();operator,info=registry(root);product=Path(info['product'])
    writable=[root/'reports'/role,root/'.sessions'/role]
    if role=='producer':writable += [root/'documents',root/'domain']
    if role=='consumer':writable += [Path(info.get('consumer_results_root',str(root/'reports/consumer')))]
    blocked=[product,operator.parent,Settings.load().file_root,Path.home()/'code/.env',root/'.sessions'/('consumer' if role=='producer' else 'producer'),root/'reports'/('consumer' if role=='producer' else 'producer')]
    if role=='consumer':blocked += [root/'documents',root/'domain']
    blocked += [Path(path) for path in info.get(role+'_denied_paths',[])]
    if role=='producer':blocked.append(Path(info.get('consumer_results_root',str(root/'reports/consumer'))))
    return '(version 1)(allow default)(deny file-write*)\n(allow file-write* '+''.join('(subpath '+json.dumps(str(p))+')' for p in writable)+'(literal "/dev/null"))\n'+''.join('(deny file-read* (subpath '+json.dumps(str(p))+'))\n' for p in blocked)


def _alive(entry):
    try:os.kill(entry['pid'],0);return True
    except (KeyError,OSError,TypeError):return False


def _reusable_channel(entry):
    """A busy live server is reusable; a probe timeout is not proof of death."""
    if not _alive(entry):return False
    try:build_opener(ProxyHandler({})).open(entry['url'],timeout=1)
    except HTTPError as error:return error.code==401
    except TimeoutError:return True
    except URLError as error:return isinstance(error.reason,TimeoutError)
    except (KeyError,OSError,ValueError):return False
    return False


def healthy(state):
    return all(_reusable_channel(state.get(role,{})) for role in ('producer','consumer')) and _alive(state.get('worker',{}))


def services(root):
    operator,info=registry(root);product=Path(info['product'])
    with (operator/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state_file=operator/'services.json'
        state={};started={}
        if state_file.exists():
            previous=json.loads(state_file.read_text())
            for role in ('producer','consumer'):
                entry=previous.get(role,{})
                if _reusable_channel(entry):state[role]=entry
                elif _alive(entry):_stop({role:entry},operator)
            if _alive(previous.get('worker',{})):state['worker']=previous['worker']
            if len(state)==3:return state
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost'}
        try:
            for role in ('producer','consumer'):
                if role in state:continue
                token=secrets.token_urlsafe(32);tokenfile=operator/(role+'.token');tokenfile.write_text(token);tokenfile.chmod(0o600)
                sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen();port=sock.getsockname()[1]
                log=(operator/(role+'.log')).open('a')
                process=subprocess.Popen([sys.executable,'-m','gsm.shared_runtime','--credentials',str(operator/(role+'.json')),'--token-file',str(tokenfile),'--fd',str(sock.fileno())],cwd=product,pass_fds=(sock.fileno(),),stdout=log,stderr=log,env={**env,'GSM_TIMING_ROLE':'developer' if role=='producer' else 'consumer'},start_new_session=True);sock.close();log.close()
                state[role]={'pid':process.pid,'url':f'http://127.0.0.1:{port}/mcp','token':token};started[role]=state[role]
            if 'worker' not in state:
                log=(operator/'worker.log').open('a')
                process=subprocess.Popen([sys.executable,'-m','gsm.cli','worker','--credentials',str(operator/'producer.json')],cwd=product,stdout=log,stderr=log,env={**env,'GSM_TIMING_ROLE':'worker'},start_new_session=True);log.close();state['worker']={'pid':process.pid};started['worker']=state['worker']
            for _ in range(100):
                if healthy(state):break
                time.sleep(.1)
            else:raise ProductError('SERVICE_START_FAILED','本地知识库服务启动失败，请检查管理员日志')
            state_file.write_text(json.dumps(state));state_file.chmod(0o600)
            return state
        except BaseException:
            _stop(started,operator);raise


def _stop(state,operator):
    for entry in state.values():
        pid=entry.get('pid')
        if not pid:continue
        command=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True).stdout
        if str(operator) not in command:continue
        try:os.kill(pid,signal.SIGINT)
        except ProcessLookupError:pass


def stop_services(root):
    operator,_=registry(root)
    with (operator/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        file=operator/'services.json'
        if file.exists():_stop(json.loads(file.read_text()),operator);file.unlink()


def client_environment(home,token,environ=None):
    source=os.environ if environ is None else environ
    allowed={'PATH','HOME','USER','LOGNAME','SHELL','LANG','LC_ALL','TERM','COLORTERM','TZ','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy','OPENAI_API_KEY','OPENAI_BASE_URL','CODEX_API_KEY'}
    result={key:value for key,value in source.items() if key in allowed}
    result.update(CODEX_HOME=str(home),TMPDIR=str(Path(home)/'tmp'),GSM_ROLE_TOKEN=token,NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost')
    return result


def launch(root,role,args):
    if sys.platform!='darwin':raise ProductError('SANDBOX_UNAVAILABLE','当前强隔离启动器仅验证macOS，其他平台需受支持的OS隔离，不自动降级')
    root=Path(root).resolve();operator,info=registry(root);policy=role_policy(root,role)
    home=root/'.sessions'/role;home.mkdir(parents=True,exist_ok=True)
    seed=Path(os.environ.get('GSM_CODEX_SEED_HOME',str(Path.home()/'.codex')))
    for name in ('auth.json','config.toml'):
        source=seed/name;dest=home/name
        if source.is_file() and not dest.exists():shutil.copyfile(source,dest);dest.chmod(0o600)
    state=services(root);profile=operator/(role+'.sb');profile.write_text(policy)
    codex=shutil.which('codex')
    if not codex:raise ProductError('CODEX_UNAVAILABLE','请安装Codex客户端；知识库初始化本身无需Codex')
    command=['/usr/bin/sandbox-exec','-f',str(profile),codex,'--dangerously-bypass-approvals-and-sandbox','--cd',str(root)]
    # Disable inherited MCPs: the only service visible to this client is its own role.
    import tomllib
    config=tomllib.loads((home/'config.toml').read_text()) if (home/'config.toml').exists() else {}
    for name in config.get('mcp_servers',{}):command+=['-c',f'mcp_servers.{name}.enabled=false']
    server='gsm_developer' if role=='producer' else 'gsm_consumer'
    for key,value in {'url':state[role]['url'],'bearer_token_env_var':'GSM_ROLE_TOKEN','enabled':True,'tool_timeout_sec':300}.items():command+=['-c',f'mcp_servers.{server}.{key}='+json.dumps(value)]
    env=client_environment(home,state[role]['token']);(home/'tmp').mkdir(exist_ok=True)
    os.chdir(root);os.execve(command[0],command+args,env)


def main():
    import argparse,uvicorn
    from .application import Application
    from .mcp.server import create_server
    p=argparse.ArgumentParser();p.add_argument('--credentials',required=True);p.add_argument('--token-file',required=True);p.add_argument('--fd',type=int,required=True);a=p.parse_args()
    app=Application(a.credentials);mcp=create_server(app);mcp.settings.stateless_http=True;mcp.settings.json_response=True;inner=mcp.streamable_http_app();token=Path(a.token_file).read_text().strip().encode()
    async def guarded(scope,receive,send):
        if scope['type']=='http' and not secrets.compare_digest(dict(scope.get('headers',[])).get(b'authorization',b''),b'Bearer '+token):
            await send({'type':'http.response.start','status':401,'headers':[]});await send({'type':'http.response.body','body':b'Unauthorized'});return
        await inner(scope,receive,send)
    uvicorn.run(guarded,fd=a.fd,log_level='warning')

if __name__=='__main__':main()
