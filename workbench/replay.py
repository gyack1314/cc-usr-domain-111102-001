"""独立重放校验器：仅凭网、日志、代价和解释逐步复演。

本模块不导入alignment或domain，发火、令牌守恒与事件消费均自行实现，
因而可作为不依赖搜索内部状态的独立裁判；校验通过只代表解释自身自洽
且为完整解释，是否最优由搜索结果的optimal状态及穷举核对另行保证。
"""


def _fail(reason, **extra):
    result = {'valid': False, 'reason': reason, 'cost': None, 'deviation_cost': None,
              'action_count': None, 'final_marking': None, 'events_consumed': None,
              'moves_checked': 0}
    result.update(extra)
    return result


def replay(net, events, costs, explanation, case_id=None, net_id=None):
    """返回{'valid': True,...}或{'valid': False,'reason':...}的裁决。

    检查项：网与事件基本结构、解释归属、逐步发火可行性与1-safe约束、
    每步令牌字段与复演一致、事件恰好按日志序消费一次、同步活动名一致、
    各动作代价与配置一致、总分与终态正确。
    """
    try:
        places = set(net['places'])
        if len(places) != len(net['places']):
            return _fail('网库所ID重复')
        table = {}
        for transition in net['transitions']:
            if transition['id'] in table:
                return _fail('网转换ID重复')
            for side in ('pre', 'post'):
                vals = transition[side]
                if len(vals) != len(set(vals)) or not set(vals) <= places:
                    return _fail('网弧定义非法')
            table[transition['id']] = transition
        for marking in (net['initial'], net['final']):
            if len(marking) != len(set(marking)) or not set(marking) <= places:
                return _fail('网标识定义非法')
        for key in ('log', 'model'):
            value = costs[key]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return _fail('代价必须为非负整数')
        sequence = list(events)
        if any(not isinstance(e.get('event_id'), str) or not e['event_id'] for e in sequence):
            return _fail('事件ID无效')
        if len({e['event_id'] for e in sequence}) != len(sequence):
            return _fail('事件ID重复')
        if explanation.get('case_id') != case_id or explanation.get('net_id') != net_id:
            return _fail('解释归属与请求票/网不一致')
    except (KeyError, TypeError) as exc:
        return _fail('输入结构非法:%s' % exc)

    marking, idx, total, moves_checked, consumed = set(net['initial']), 0, 0, 0, []
    allowed = {'sync', 'log', 'model'}
    for move in explanation.get('moves', []):
        try:
            kind, tid, eid = move['type'], move['transition_id'], move['event_id']
        except (KeyError, TypeError):
            return _fail('动作字段缺失', moves_checked=moves_checked)
        if kind not in allowed:
            return _fail('未知动作类型', moves_checked=moves_checked)
        if move.get('tokens_before') != sorted(marking):
            return _fail('动作前令牌与复演不一致', moves_checked=moves_checked)
        if kind == 'log':
            if tid != '':
                return _fail('log动作不得引用转换', moves_checked=moves_checked)
            if idx >= len(sequence) or eid != sequence[idx]['event_id']:
                return _fail('log动作未按日志序引用当前事件', moves_checked=moves_checked)
            expected_cost = costs['log']
            after = set(marking)
            idx += 1
        else:
            transition = table.get(tid)
            if transition is None:
                return _fail('动作引用不存在的转换', moves_checked=moves_checked)
            pre, post = set(transition['pre']), set(transition['post'])
            if not pre <= marking or (marking - pre) & post:
                return _fail('转换不满足发火条件或会重复占用后置库所', moves_checked=moves_checked)
            after = (marking - pre) | post  # 1-safe：上面的检查保证后置库所原先无令牌
            if kind == 'sync':
                if transition['label'] is None:
                    return _fail('静默转换不能做同步动作', moves_checked=moves_checked)
                if idx >= len(sequence) or eid != sequence[idx]['event_id']:
                    return _fail('sync动作未按日志序引用当前事件', moves_checked=moves_checked)
                if sequence[idx]['activity'] != transition['label']:
                    return _fail('sync动作活动名与事件不一致', moves_checked=moves_checked)
                expected_cost = 0
                idx += 1
            else:
                if eid != '':
                    return _fail('model动作不得引用事件', moves_checked=moves_checked)
                expected_cost = 0 if transition['label'] is None else costs['model']
        if move.get('cost') != expected_cost:
            return _fail('动作偏差代价与配置不符', moves_checked=moves_checked)
        if move.get('tokens_after') != sorted(after):
            return _fail('动作后令牌与复演不一致', moves_checked=moves_checked)
        total += expected_cost
        if eid:
            consumed.append(eid)
        marking, moves_checked = after, moves_checked + 1

    if idx != len(sequence):
        return _fail('日志事件未被全部消费', moves_checked=moves_checked)
    if len(set(consumed)) != len(consumed):
        return _fail('事件被重复消费', moves_checked=moves_checked)
    if set(marking) != set(net['final']):
        return _fail('复演终态与指定终态不符', moves_checked=moves_checked,
                     final_marking=sorted(marking))
    if explanation.get('cost') != total or explanation.get('deviation_cost') != total:
        return _fail('解释总分与逐步重放不符', moves_checked=moves_checked, cost=total)
    if explanation.get('action_count') != moves_checked:
        return _fail('解释动作数与明细不符', moves_checked=moves_checked)
    if explanation.get('events_consumed') != consumed:
        return _fail('解释的事件消费清单与重放不符', moves_checked=moves_checked)
    if explanation.get('final_marking') != sorted(marking):
        return _fail('解释终态字段与重放不符', moves_checked=moves_checked,
                     final_marking=sorted(marking))
    return {'valid': True, 'reason': None, 'cost': total, 'deviation_cost': total,
            'action_count': moves_checked, 'final_marking': sorted(marking),
            'events_consumed': consumed, 'moves_checked': moves_checked}
