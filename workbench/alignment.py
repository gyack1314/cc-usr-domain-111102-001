"""流程合规对齐：在1-safe Petri网与全序日志的乘积状态空间上求最小代价完整解释。

动作三类（决胜顺序见docs/domain.md）：
sync  同名活动与可见转换同步消费，代价0；
log   只消费日志事件，代价取配置log；
model 只推进流程：静默转换代价0，可见转换取配置model。
相同代价先比动作数，再比（动作类型、转换ID、事件ID）序列字典序，
类型顺序固定为sync、log、model，缺失ID以空串参与比较。
"""
import heapq
from .domain import enabled, validate_net

SYNC, LOG, MODEL = 'sync', 'log', 'model'
TYPE_ORDER = {SYNC: 0, LOG: 1, MODEL: 2}
OPTIMAL = 'optimal'
UNREACHABLE = 'unreachable'
INVALID_NET = 'invalid_net'
RESOURCE_EXHAUSTED = 'resource_exhausted'
_TERMINAL = {UNREACHABLE, INVALID_NET, RESOURCE_EXHAUSTED}


def validate_events(rows):
    """校验事件并按case_id分组、组内按sequence排序。"""
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('事件应为对象数组')
    seen, cases = set(), {}
    for row in rows:
        for key in ('event_id', 'case_id', 'sequence', 'activity'):
            if key not in row:
                raise ValueError('事件字段缺失')
        eid, cid = row['event_id'], row['case_id']
        if not isinstance(eid, str) or not eid or not isinstance(cid, str) or not cid:
            raise ValueError('事件ID无效')
        if eid in seen:
            raise ValueError('事件ID重复')
        seen.add(eid)
        if not isinstance(row['activity'], str) or not row['activity']:
            raise ValueError('活动名无效')
        seq = row['sequence']
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
            raise ValueError('sequence无效')
        cases.setdefault(cid, []).append(row)
    for group in cases.values():
        seqs = [r['sequence'] for r in group]
        if len(seqs) != len(set(seqs)):
            raise ValueError('票内sequence重复')
        group.sort(key=lambda r: r['sequence'])
    return cases


def validate_costs(costs):
    result = {}
    for key in ('log', 'model'):
        value = costs.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError('代价必须为非负整数')
        result[key] = value
    limit = costs.get('search_limit', 100000)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError('search_limit必须为正整数')
    result['search_limit'] = limit
    return result


def _fire(marking, transition):
    return frozenset((marking - frozenset(transition['pre'])) | frozenset(transition['post']))


def _base(case_id, net_id, status, complete, limit, expanded):
    return {'case_id': case_id, 'net_id': net_id, 'status': status, 'complete': complete,
            'cost': None, 'deviation_cost': None, 'action_count': None,
            'final_marking': None, 'events_consumed': [], 'moves': [],
            'expanded': expanded, 'search_limit': limit, 'error': None}


def _exhausted(case_id, net_id, limit, expanded):
    result = _base(case_id, net_id, RESOURCE_EXHAUSTED, False, limit, expanded)
    result['error'] = '搜索资源耗尽，未证明最优也未证明无解'
    return result


def _invalid(case_id, net_id, limit, error):
    result = _base(case_id, net_id, INVALID_NET, False, limit, 0)
    result['error'] = error
    return result


def _build_optimal(net, events, costs, path, total, expanded, limit, case_id, net_id):
    by_id = {t['id']: t for t in net['transitions']}
    marking, idx, moves, consumed = frozenset(net['initial']), 0, [], []
    for step, (code, tid, eid) in enumerate(path, 1):
        before = sorted(marking)
        if code == TYPE_ORDER[LOG]:
            event = events[idx]
            if eid != event['event_id']:
                raise ValueError('内部解释引用事件不一致')
            moves.append({'step': step, 'type': LOG, 'transition_id': '', 'event_id': eid,
                          'activity': event['activity'], 'cost': costs['log'],
                          'tokens_before': before, 'tokens_after': list(before)})
            consumed.append(eid)
            idx += 1
            continue
        transition = by_id[tid]
        after = _fire(marking, transition)
        if code == TYPE_ORDER[SYNC]:
            event = events[idx]
            if eid != event['event_id']:
                raise ValueError('内部解释引用事件不一致')
            moves.append({'step': step, 'type': SYNC, 'transition_id': tid, 'event_id': eid,
                          'activity': transition['label'], 'cost': 0,
                          'tokens_before': before, 'tokens_after': sorted(after)})
            consumed.append(eid)
            idx += 1
        else:
            moves.append({'step': step, 'type': MODEL, 'transition_id': tid, 'event_id': '',
                          'activity': transition['label'], 'cost': 0 if transition['label'] is None else costs['model'],
                          'tokens_before': before, 'tokens_after': sorted(after)})
        marking = after
    result = _base(case_id, net_id, OPTIMAL, True, limit, expanded)
    result.update({'cost': total, 'deviation_cost': total, 'action_count': len(moves),
                   'final_marking': sorted(marking), 'events_consumed': consumed, 'moves': moves})
    return result


def align(net, events, costs, case_id=None, net_id=None):
    """消费全部事件并到达net['final']，返回最小代价解释。

    网须先经domain.validate_net校验。状态为（标识, 下一事件下标），
    1-safe保证标识为库所子集，状态空间有界，零代价静默环由闭合表剪枝。
    """
    costs = validate_costs(costs)
    validate_net(net)  # 防御直接调用：非法网抛ValueError，批处理由safe_align转结果
    if not isinstance(events, list):
        raise ValueError('事件应为对象数组')
    limit = costs['search_limit']
    initial, target = frozenset(net['initial']), frozenset(net['final'])
    transitions, n = net['transitions'], len(events)
    # 堆项：（累计代价, 动作数, 字典序路径, 唯一序号, 标识, 事件下标）
    heap, serial, done, expanded = [(0, 0, (), 0, initial, 0)], 1, {}, 0
    while heap:
        g, count, path, _, marking, idx = heapq.heappop(heap)
        key = (marking, idx)
        if key in done and done[key] <= (g, count):
            continue
        if idx == n and marking == target:
            return _build_optimal(net, events, costs, path, g, expanded, limit, case_id, net_id)
        done[key] = (g, count)
        expanded += 1
        if expanded > limit:
            return _exhausted(case_id, net_id, limit, expanded)
        successors = []
        if idx < n:  # 只消费日志：标识不变
            eid = events[idx]['event_id']
            successors.append((g + costs['log'], count + 1,
                               path + ((TYPE_ORDER[LOG], '', eid),), marking, idx + 1))
        for transition in transitions:  # 定义序生成，堆序保证结果与枚举顺序无关
            if not enabled(set(marking), transition):
                continue
            tid, after = transition['id'], _fire(marking, transition)
            silent = transition['label'] is None
            if idx < n and not silent and transition['label'] == events[idx]['activity']:
                successors.append((g, count + 1,
                                   path + ((TYPE_ORDER[SYNC], tid, events[idx]['event_id']),),
                                   after, idx + 1))
            move_cost = 0 if silent else costs['model']
            successors.append((g + move_cost, count + 1,
                               path + ((TYPE_ORDER[MODEL], tid, ''),), after, idx))
        for g2, count2, path2, marking2, idx2 in successors:
            heapq.heappush(heap, (g2, count2, path2, serial, marking2, idx2))
            serial += 1
    result = _base(case_id, net_id, UNREACHABLE, True, limit, expanded)
    result['error'] = '乘积状态空间已穷尽，无法消费全部事件并到达终态'
    return result


def safe_align(net, events, costs, case_id=None, net_id=None):
    """与align相同，但把非法网转换为invalid_net结果而非抛出异常。

    代价与事件的配置错误不属于网非法，仍按ValueError上抛给批处理入口。
    """
    try:
        net = validate_net(net)
    except ValueError as exc:
        try:
            limit = validate_costs(costs)['search_limit']
        except ValueError:
            limit = None
        return _invalid(case_id, net_id, limit, str(exc))
    return align(net, events, costs, case_id, net_id)


def align_all(nets, event_rows, costs_row, net_id=None, case_ids=None):
    """批处理：按票分组，对每张（或指定）网逐票对齐。"""
    cases = validate_events(event_rows)
    costs = validate_costs(costs_row)
    chosen = [n for n in nets if net_id is None or n.get('id') == net_id]
    if net_id is not None and not chosen:
        raise ValueError('未找到指定网ID')
    wanted = list(cases) if case_ids is None else case_ids
    missing = [c for c in wanted if c not in cases]
    if missing:
        raise ValueError('未找到指定票ID:%s' % ','.join(missing))
    results = []
    for net in chosen:
        nid = net.get('id')
        for cid in wanted:
            results.append(safe_align(net, cases[cid], costs, cid, nid))
    return {'cost_id': costs_row.get('id'), 'results': results}
