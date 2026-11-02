import argparse,json,time
from pathlib import Path
from .application import Application
from .config import Settings
from .store import Store


def main():
    parser=argparse.ArgumentParser(prog='gsm')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('migrate')
    shared=commands.add_parser('init-kb');shared.add_argument('--root',required=True);shared.add_argument('--name',default='我的知识库')
    init=commands.add_parser('init-workspaces');init.add_argument('--root',required=True)
    for name in ('serve','worker'):
        command=commands.add_parser(name);command.add_argument('--credentials',required=True)
        if name=='worker':
            command.add_argument('--once');command.add_argument('--kb-id')
    args=parser.parse_args()
    if args.command=='init-kb':
        from .workspaces import initialize_kb
        print(json.dumps(initialize_kb(Path(args.root),args.name),ensure_ascii=False,indent=2));return
    if args.command=='init-workspaces':
        from .workspaces import provision
        print(json.dumps(provision(Path(args.root)),ensure_ascii=False,indent=2));return
    if args.command=='migrate':Store(Settings.load()).migrate();return
    app=Application(args.credentials)
    if args.command=='serve':
        from .mcp.server import create_server
        create_server(app).run(transport='stdio')
    elif args.once:
        print(json.dumps(app.execute_task(args.kb_id,args.once),ensure_ascii=False))
    else:
        if app.principal.role!='developer':raise SystemExit('worker requires developer credentials')
        while True:
            for kb_id in sorted(app.principal.kb_ids):
                with app.store.transaction(app.principal,kb_id) as conn:
                    rows=conn.execute("SELECT id FROM tasks WHERE kb_id=%s AND status IN ('queued','running') ORDER BY updated_at LIMIT 5",(kb_id,)).fetchall()
                for row in rows:
                    from .errors import ProductError
                    try:app.execute_task(kb_id,str(row[0]))
                    except ProductError as error:
                        if error.code!='TASK_BUSY':raise
            time.sleep(1)

if __name__=='__main__':main()
