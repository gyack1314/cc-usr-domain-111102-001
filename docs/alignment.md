# 流程合规对齐约定

在workbench/domain.py的网原语之上，alignment.py把每票货的全序日志与1-safe Petri网做乘积搜索，为每票货找一条“消费全部事件并到达终态”的完整解释；replay.py不导入搜索与网原语模块，仅凭输入文件独立复演解释。

## 动作与代价

状态为（当前标识，下一事件下标），标识是库所ID的无序子集（1-safe）。每步只允许三类动作，决胜顺序固定：

| 动作 | 含义 | 转换ID | 事件ID | 代价 |
| --- | --- | --- | --- | --- |
| sync | 同名可见转换与当前事件同步推进 | 实际转换ID | 当前事件ID | 0 |
| log | 只消费日志事件，标识不变 | 空串 | 当前事件ID | costs.log |
| model | 只发火转换推进流程 | 实际转换ID | 空串 | 静默0，可见为costs.model |

静默转换（label=null）只能走model。sync要求事件activity与转换label逐字相等；重复标签必须落到具体转换ID，解释里不允许只写活动名。代价只接受非负整数。

## 最优性与决胜

目标是消费全部日志且标识等于net.final时总代价最小，提前到达终态但仍有未消费事件不算结束。同一状态先被更差键值展开时会被后续更优键值覆盖重展；Dijkstra式按累计代价出栈保证首个命中终态的完整解释最优。

同代价再比动作数，仍相同则比较动作序列字典序：先动作类型（sync<log<model），再transition_id，再event_id，缺失ID以空串比较。因此并行分支的两种换序、重复标签的两个候选转换都有确定唯一答案。

## 结果状态

- optimal：已证明最优的完整解释，含moves逐步明细、tokens_before/tokens_after、event_id/transition_id引用、每步cost、总分与终态。
- unreachable：乘积状态空间完整穷尽（complete=true）仍无解，区别于没搜完。
- invalid_net：网定义非法，expanded为0并带error。
- resource_exhausted：展开数超过costs.search_limit，complete=false，不得报告最优或无解。

零代价静默环不会无限展开：（标识，下标）相同即同一状态，闭合表直接剪枝；环上任何路径都不可能比无环路径更优。

## 独立重放

replay.replay自行实现发火与1-safe检查，不导入alignment、domain和brute_force。它逐步核对：发火前置令牌齐备且后置库所未被占用、明细令牌字段与复演一致、事件严格按日志序且恰好消费一次、sync活动名一致、每步代价与配置一致、总分与终态字段一致。重放只证明解释自洽完整，最优性由搜索状态与穷举核对（brute_force，仅测试与小网使用）保证。

## 批处理入口

```
python -m workbench.cli align nets.json events.json costs.json --output out.json [--net ID] [--cases A B] [--cost-row 0]
python -m workbench.cli verify nets.json events.json costs.json out.json
```

align接收对象数组文件；events按case_id分组、组内按sequence排序，sequence是业务确认的全序，不按接收时间改排。全部optimal时退出码0，存在非optimal状态时退出码3，文件或字段错误退出码2。verify可吃align的整包输出或单条解释。
