# 港口作业事件的并行流程合规对齐资料库

作业活动与令牌网的读取、定义检查、单步模拟与流程合规对齐库。资料在samples，数据语义见docs/domain.md，对齐语义见docs/alignment.md，本地存档说明见docs/catalog.md。全部为本地虚构合成数据，不连接真实港口系统。

## 运行

需要Python 3.11以上，仅使用标准库。

```bash
python -m workbench.cli inspect samples
python -m workbench.cli ingest samples state/raw.sqlite3
python -m workbench.cli catalog state/raw.sqlite3
python -m workbench.cli align samples/nets.json samples/events.json samples/costs.json --output state/aligned.json
python -m workbench.cli verify samples/nets.json samples/events.json samples/costs.json state/aligned.json
python -m examples.run_examples
python -m unittest discover -s tests -v
python -m compileall -q workbench tests examples
```

inspect查看文件行数和摘要；ingest将原始包放入SQLite；catalog列出原始包。align对每票货在（标识，事件下标）乘积空间上求最小代价完整解释：sync零代价、log只消费事件、model只推进流程（静默转换零代价），同代价先比动作数再按sync/log/model与转换、事件ID字典序决胜。verify用不依赖搜索内部状态的独立重放校验器复演解释，核对令牌守恒、事件恰好消费一次、总分与终态。

## 例子覆盖

- A票：场内检查先于单证核验，并行换序零代价，不再误判倒序；
- B票：缺少放行事件，放行以可见model动作定位为偏差，代价3；
- C票：重复扫描触发一次log偏差加一次可见model偏差，共5；
- D票（examples/events_rework.json）：返工环整体零代价复演；
- examples/nets_small.json：线性、并行、重复标签小网，测试用穷举器逐网逐票核对最优性。

不可达终态、非法网、搜索资源耗尽分别返回unreachable、invalid_net、resource_exhausted；未搜完不会报告最优或无解，零代价静默环由闭合状态剪枝。CLI在全部optimal时退出0，存在非optimal结果时退出3，文件错误退出2。

## 容器

```bash
docker build -t local-workbench .
docker run --rm --network none local-workbench
docker run --rm --network none local-workbench python -m unittest discover -s tests -v
```

程序不需要外部账号或常驻服务，容器默认查看合成资料。state与output为本地工作目录，不进入版本控制。workbench/io.py负责JSON与文件边界，catalog.py负责原始资料事务，domain.py提供网原语，alignment.py负责对齐搜索，replay.py是独立重放裁判，brute_force.py仅供测试穷举核对。
