"""端到端可运行例子：对齐搜索 + 独立重放 + 穷举最优性核对。

在仓库根目录执行：
    python -m examples.run_examples
不连接任何真实港口系统，全部为虚构合成数据。
"""
from pathlib import Path

from workbench.alignment import align, align_all
from workbench.brute_force import brute_force_optimum
from workbench.domain import validate_net
from workbench.io import read_json
from workbench.replay import replay

ROOT = Path(__file__).resolve().parents[1]


def _brief(result):
    moves = []
    for move in result['moves']:
        ref = move['event_id'] or move['transition_id']
        moves.append('%s:%s(+%s)' % (move['type'], ref, move['cost']))
    return '状态=%s 代价=%s 动作数=%s | %s' % (
        result['status'], result['cost'], result['action_count'], ' '.join(moves))


def main():
    nets = read_json(ROOT / 'samples/nets.json')
    events = read_json(ROOT / 'samples/events.json')
    costs = read_json(ROOT / 'samples/costs.json')[0]
    rework_events = read_json(ROOT / 'examples/events_rework.json')
    small_nets = read_json(ROOT / 'examples/nets_small.json')
    small_events = read_json(ROOT / 'examples/events_small.json')

    print('== 虚构码头主网：A 并行换序 / B 遗漏放行 / C 重复扫描 ==')
    bundle = align_all(nets, events, costs)
    for result in bundle['results']:
        print(result['case_id'], _brief(result))
        verdict = replay(nets[0], [e for e in events if e['case_id'] == result['case_id']],
                         costs, result, result['case_id'], result['net_id'])
        assert verdict['valid'], verdict
        assert verdict['cost'] == result['cost']

    print('\n== D 返工环：返工后重新双分支检查 ==')
    rework = align(validate_net(nets[0]), rework_events, costs, 'D', 'port')
    print('D', _brief(rework))
    verdict = replay(nets[0], rework_events, costs, rework, 'D', 'port')
    assert verdict['valid'] and verdict['cost'] == 0, verdict

    print('\n== 小网穷举核对最优性与决胜序列 ==')
    by_case = {}
    for event in small_events:
        by_case.setdefault(event['case_id'], []).append(event)
    expectations = {'S1': (0, None), 'S2': (10, None), 'S3': (5, None)}
    for net in small_nets:
        for cid, rows in by_case.items():
            result = align(validate_net(net), rows, costs, cid, net['id'])
            opt = brute_force_optimum(net, rows, costs)
            if opt is None:
                assert result['status'] == 'unreachable', (cid, net['id'], result)
                print('%s@%s 无解：搜索与穷举一致' % (cid, net['id']))
                continue
            assert result['status'] == 'optimal'
            assert result['cost'] == opt[0] and result['action_count'] == opt[1], (cid, net['id'])
            verdict = replay(net, rows, costs, result, cid, net['id'])
            assert verdict['valid'], verdict
            print('%s@%s 代价=%s 动作数=%s 与穷举一致' % (cid, net['id'], opt[0], opt[1]))
    for cid, (cost, _) in expectations.items():
        result = align(validate_net(small_nets[0]), by_case[cid], costs, cid, 'linear')
        assert result['cost'] == cost, (cid, result)

    print('\n全部例子与断言通过。')
    return bundle, rework


if __name__ == '__main__':
    main()
