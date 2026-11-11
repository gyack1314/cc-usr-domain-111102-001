# 领域数据约定

库所及转换ID为非空字符串；marking为无重复库所ID列表，1-safe令牌数只能为0或1。transition含id、label、pre、post，label=null表示静默，pre/post不重复且允许同一库所同时出现。发火先消耗pre再加入post，禁止加入仍被占用的库所。动作类型决胜顺序sync、log、model；每项随后比较transition_id（不存在为空串）、event_id（不存在为空串）。事件sequence各票内唯一，event_id全包唯一。search_limit为调用者资源上限，不改变网的语言。

全部资料为本地合成。samples保留来源状态，读取和存档不等于业务验证通过；异常记录不被自动修改。workbench/domain.py中的现有函数可独立调用，tests/domain_checks.py演示其行为。
