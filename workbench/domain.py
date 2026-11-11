def validate_net(net):
    places=net['places'];ids=[x['id'] for x in net['transitions']]
    if len(places)!=len(set(places)) or len(ids)!=len(set(ids)):raise ValueError('定义ID重复')
    if any(not isinstance(x,str) or not x for x in places+ids):raise ValueError('定义ID无效')
    for marking in [net['initial'],net['final']]:
        if len(marking)!=len(set(marking)) or not set(marking)<=set(places):raise ValueError('标识无效')
    for t in net['transitions']:
        if t['label'] is not None and not isinstance(t['label'],str):raise ValueError('活动名无效')
        for side in ['pre','post']:
            if len(t[side])!=len(set(t[side])) or not set(t[side])<=set(places):raise ValueError('弧无效')
    return net

def enabled(marking,transition):
    marking=set(marking);pre=set(transition['pre']);post=set(transition['post'])
    return pre<=marking and not ((marking-pre)&post)

def fire(marking,transition):
    if not enabled(marking,transition):raise ValueError('转换不可发火')
    return sorted((set(marking)-set(transition['pre']))|set(transition['post']))
