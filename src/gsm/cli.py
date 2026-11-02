import argparse,json,time
from pathlib import Path
from .application import Application
from .config import Settings
from .store import Store


def main():
    parser=argparse.ArgumentParser(prog='gsm')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('migrate')
    shared=commands.add_parser('init-kb');shared.add_argument('--root',required=True);shared.add_argument('--name',default='我的知识库');shared.add_argument('--producer-deny-read',action='append',default=[]);shared.add_argument('--consumer-deny-read',action='append',default=[]);shared.add_argument('--consumer-results')
    configure=commands.add_parser('configure-kb');configure.add_argument('--root',required=True);configure.add_argument('--consumer-results',required=True)
    launch=commands.add_parser('launch-kb');launch.add_argument('--root',required=True);launch.add_argument('--role',choices=['producer','consumer'],required=True);launch.add_argument('extra',nargs=argparse.REMAINDER)
    stop=commands.add_parser('stop-kb');stop.add_argument('--root',required=True)
    init=commands.add_parser('init-workspaces');init.add_argument('--root',required=True)
    for name in ('serve','worker'):
        command=commands.add_parser(name);command.add_argument('--credentials',required=True)
        if name=='worker':
            command.add_argument('--once');command.add_argument('--kb-id')
    args=parser.parse_args()
    if args.command=='configure-kb':
        from .workspaces import configure_shared_runtime
        print(json.dumps(configure_shared_runtime(Path(args.root),consumer_results_root=args.consumer_results),ensure_ascii=False));return
    if args.command=='launch-kb':
        from .shared_runtime import launch
        extra=args.extra[1:] if args.extra[:1]==['--'] else args.extra
        launch(Path(args.root),args.role,extra);return
    if args.command=='stop-kb':
        from .shared_runtime import stop_services
        stop_services(Path(args.root));return
    if args.command=='init-kb':
        from .workspaces import initialize_kb
        print(json.dumps(initialize_kb(Path(args.root),args.name,producer_denied_paths=args.producer_deny_read,consumer_denied_paths=args.consumer_deny_read,consumer_results_root=args.consumer_results),ensure_ascii=False,indent=2));return
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
