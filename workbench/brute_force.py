"""小规模乘积状态空间穷举，供测试核对Dijkstra最优性，不参与生产搜索。

深度优先枚举全部无重复状态的路径（状态空间有限，故不漏解），
返回（最小代价, 最少动作数, 字典序最小动作路径）；无解返回None。
"""
from .domain import enabled

SYNC, LOG, MODEL = 0, 1, 2
_INF = 10 ** 18


def brute_force_optimum(net, events, costs):
    costs = {'log': costs['log'], 'model': costs['model']}
    transitions = net['transitions']
    initial, target = frozenset(net['initial']), frozenset(net['final'])
    n = len(events)

    def successors(marking, idx):
        out = []
        if idx < n:
            eid = events[idx]['event_id']
            out.append(((LOG, '', eid), costs['log'], marking, idx + 1))
        for transition in transitions:
            if not enabled(set(marking), transition):
                continue
            tid, after = transition['id'], frozenset(
                (marking - frozenset(transition['pre'])) | frozenset(transition['post']))
            silent = transition['label'] is None
            if idx < n and not silent and transition['label'] == events[idx]['activity']:
                out.append(((SYNC, tid, events[idx]['event_id']), 0, after, idx + 1))
            out.append(((MODEL, tid, ''), 0 if silent else costs['model'], after, idx))
        out.sort(key=lambda item: item[0])
        return out

    memo = {}

    def search(marking, idx, on_path):
        key = (marking, idx)
        if key in memo:
            return memo[key]
        if idx == n and marking == target:
            return 0, 0, ()
        on_path.add(key)
        best = None
        for edge, edge_cost, marking2, idx2 in successors(marking, idx):
            if (marking2, idx2) in on_path:  # 回到路径上的状态只会成环，严格更优不可能
                continue
            sub = search(marking2, idx2, on_path)
            if sub is None:
                continue
            candidate = (edge_cost + sub[0], 1 + sub[1], (edge,) + sub[2])
            if best is None or (candidate[0], candidate[1], candidate[2]) < best:
                best = candidate
        on_path.discard(key)
        memo[key] = best
        return best

    return search(initial, 0, set())
