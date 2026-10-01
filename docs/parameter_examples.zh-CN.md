# 类型化参数示例

[English](parameter_examples.md) · [当前生效定义](../parameters.json) · [严格 JSON 副本](parameter_examples.json)

当前 `parameters.json` 选了 20 个有代表性的原生 `SamplingParams` 字段。`jev_requests.py` 读取每项的 `type` 与 `control`，生成对应类型的 Choice。链接中的完整 JSON 是语法示例；改变实验须修改当前生效文件。旧版 `adjustments` 触发规则不再接受。

- **小数：**`temperature=0.6`，调控窗口 `[0,2]`、分母 20。先选保持／增加／减少；增加后给出 0.7、0.8、0.9 三个具体值，减少则给出 0.5、0.4、0.3。`top_p`、`repetition_penalty`、`frequency_penalty`、`presence_penalty`、`min_p` 各自使用配置中的窗口和分母。
- **整数：**`top_k=20`，实用窗口 `[1,101]`、分母 20，因此一步为 5；增加候选为 25、30、35。它另有单独的“关闭”动作，把值设为 0；再“启用”时回到 20。硬边界仍是 `[-1,1000000]`，不能拿一百万当作步长窗口。接近边界时删除越界或重复的候选。
- **布尔：**`ignore_eos=false` 时只有保持／打开；为 true 时只有保持／关闭。选中切换后目标值已确定，无需第三次 Jev 请求。
- **可空列表：**`stop_token_ids` 和 `allowed_token_ids` 需要分词器核实过的整数 ID，后者不能设置为空列表。已有列表时可移除元素或清空。Jev 不能凭空写入列表元素。
- **可空映射：**`logit_bias=null` 要先填写核实过的 `control.entries`，每项包含整数 `token_id` 与有界数值 `value`。JSON 记录使用字符串键，后端在构造原生参数前转回整数 ID；已有映射时可删一项或清空。添加前应以实际模型分词器核对 token ID。
- **枚举：**`output_kind` 初始为 `CUMULATIVE`，可切换到声明的另一个合法选项 `FINAL_ONLY`。后端把 JSON 字符串转换为 vLLM 原生枚举。
- **可空整数：**`logprobs=null` 和 `prompt_logprobs=null` 可从核实过的 `0`、`1`、`2` 中选择启用起点。启用后，窗口 `[0,20]`、分母 20 给出整数步长 1：当前为 1 时，增加候选为 2、3、4，减少候选为 0，也可关闭回到 `null`。它们是观测设置，不是 Jev Score，也不是答案质量调控。
- **其他容易切换的字段：**`min_tokens` 只在 `0` 和 `1` 之间切换，确保只剩一个 token 生成空间时仍合法；`detokenize`、`skip_special_tokens`、`spaces_between_special_tokens`、`include_stop_str_in_output`、`flat_logprobs` 均为布尔开关。后几项改变观测或输出形式，依赖功能未启用时有的切换不会产生效果。

每次方向请求的上下文都包含当前 20 个值。目前 17 项有可执行方向；只有 `stop_token_ids`、`allowed_token_ids` 和 `logit_bias` 要先补经核实的 token 候选，暂时只能保持。技术上能修改，不等于适合用来纠正错误答案。

新增参数还须是已安装 `SamplingParams` 真正接受的字段；`python run.py doctor` 只构造参数，不加载模型、不调用 Jev。[完整清单](vllm_catalog_taxonomy.zh-CN.md)中的条件性功能或启动字段，要另外实现相应接口后才能进入这里。
