from workbench.domain import validate_net,enabled,fire
def check(c,root,read):
    net=validate_net(read(root/'samples/nets.json')[0]);t=net['transitions'][0]
    c.assertEqual(fire(['start'],t),['docs','yard'])
    c.assertFalse(enabled(['docs'],t))
    with c.assertRaises(ValueError):fire(['docs'],t)
    c.assertEqual(fire(['a'],{'pre':['a'],'post':['a']}),['a'])
    c.assertFalse(enabled(['a','b'],{'pre':['a'],'post':['b']}))
