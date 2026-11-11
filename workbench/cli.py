import argparse
import json
import sys
from .alignment import align_all
from .catalog import Catalog
from .io import inspect_bundle, read_json, write_json
from .replay import replay


def _run_align(args):
    nets = read_json(args.nets)
    events = read_json(args.events)
    costs = read_json(args.costs)[0] if args.cost_row is None else read_json(args.costs)[args.cost_row]
    result = align_all(nets, events, costs, net_id=args.net, case_ids=args.cases)
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(r['status'] == 'optimal' for r in result['results']) else 3


def _run_verify(args):
    nets = read_json(args.nets)
    events = read_json(args.events)
    costs = read_json(args.costs)[0] if args.cost_row is None else read_json(args.costs)[args.cost_row]
    payload = read_json(args.explanation)
    explanations = payload['results'] if isinstance(payload, dict) and 'results' in payload else [payload]
    net_table = {n.get('id'): n for n in nets}
    groups = {}
    for event in events:
        groups.setdefault(event['case_id'], []).append(event)
    for group in groups.values():
        group.sort(key=lambda row: row['sequence'])
    verdicts, ok = [], True
    for explanation in explanations:
        if explanation.get('net_id') not in net_table or explanation.get('case_id') not in groups:
            raise ValueError('解释引用了未知网或票')
        net = net_table[explanation['net_id']]
        case = groups[explanation['case_id']]
        verdict = replay(net, case, costs, explanation, explanation['case_id'], explanation['net_id'])
        verdict.update({'case_id': explanation['case_id'], 'net_id': explanation['net_id']})
        verdicts.append(verdict)
        ok = ok and verdict['valid']
    out = {'all_valid': ok, 'verdicts': verdicts}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok else 3


def main():
    parser = argparse.ArgumentParser(description='业务资料读取、本地存档与流程合规对齐')
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('inspect'); p.add_argument('directory')
    p = subs.add_parser('ingest'); p.add_argument('directory'); p.add_argument('database')
    p = subs.add_parser('catalog'); p.add_argument('database')
    p = subs.add_parser('align', help='对一票或多票货做流程合规对齐')
    p.add_argument('nets'); p.add_argument('events'); p.add_argument('costs')
    p.add_argument('--cost-row', type=int, default=None)
    p.add_argument('--net', default=None); p.add_argument('--cases', nargs='*', default=None)
    p.add_argument('--output', required=True); p.set_defaults(func=_run_align)
    p = subs.add_parser('verify', help='用独立重放校验器复演对齐解释')
    p.add_argument('nets'); p.add_argument('events'); p.add_argument('costs')
    p.add_argument('explanation'); p.add_argument('--cost-row', type=int, default=None)
    p.set_defaults(func=_run_verify)
    args = parser.parse_args()
    try:
        if args.command == 'inspect':
            result = inspect_bundle(args.directory)
            print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
        if args.command == 'ingest':
            result = {'import_id': Catalog(args.database).ingest(args.directory)}
            print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
        if args.command == 'catalog':
            print(json.dumps(Catalog(args.database).summary(), ensure_ascii=False, indent=2)); return 0
        return args.func(args)
    except (ValueError, OSError, KeyError, IndexError):
        print('资料读取失败，请核对文件与字段约定', file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())
