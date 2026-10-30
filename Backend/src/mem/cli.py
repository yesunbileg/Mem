import argparse,json,sys
from dataclasses import asdict,is_dataclass
from pathlib import Path
from .errors import MemoryError

def output(value):
    if hasattr(value,'model_dump'):value=value.model_dump(mode='json')
    elif is_dataclass(value):value=asdict(value)
    print(json.dumps(value,ensure_ascii=False,default=str))

def main():
    parser=argparse.ArgumentParser(description='Local source-backed memory')
    parser.add_argument('--root',type=Path)
    subs=parser.add_subparsers(dest='command',required=True)
    for command in ['init','serve','reindex','verify','recover']:subs.add_parser(command)
    backup=subs.add_parser('backup');backup.add_argument('--output',type=Path,required=True)
    subs.add_parser('snapshot')
    restore=subs.add_parser('restore');restore.add_argument('--backup',type=Path,required=True);restore.add_argument('--destination',type=Path,required=True)
    rs=subs.add_parser('restore-snapshot');rs.add_argument('--snapshot',type=Path,required=True);rs.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    if not args.root and args.command not in ('restore','restore-snapshot'):parser.error('--root is required')
    try:
        if args.command in ('restore','restore-snapshot'):
            from .backup import restore_backup,restore_snapshot
            if args.command=='restore':output(restore_backup(args.backup,args.destination))
            else:restore_snapshot(args.snapshot,args.destination);output({'restored':str(args.destination)})
            return 0
        if args.command=='serve':
            from .server import create_server
            create_server(args.root).run(transport='stdio');return 0
        from .store import init_store,open_store
        from .health import get_health
        from .recovery import recover_pending
        from .index import rebuild_index
        with (init_store if args.command=='init' else open_store)(args.root) as store:
            if args.command=='backup':
                from .backup import create_backup
                result=create_backup(store,args.output)
            elif args.command=='snapshot':
                from .backup import create_snapshot
                result={'snapshot':str(create_snapshot(store))}
            elif args.command=='reindex':result=rebuild_index(store)
            elif args.command=='recover':result=recover_pending(store)
            else:result=get_health(store,deep=True)
            output(result)
            if args.command=='verify' and not result.ready:return 1
            if args.command=='recover' and result.conflicts:return 1
        return 0
    except MemoryError as e:
        print(json.dumps(dict(code=e.code,message=e.message,details=e.details)),file=sys.stderr);return 1
    except (OSError,ValueError):
        print(json.dumps(dict(code='IO_OR_VALIDATION_ERROR',message='Command failed; check paths and input')),file=sys.stderr);return 1

if __name__=='__main__':sys.exit(main())
