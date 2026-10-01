# 从 Transformers 迁移到原生 vLLM：哪些概念不能照搬

[English](transformers_to_vllm.md) · [当前实现](implementation.zh-CN.md) · [启用的参数定义](../parameters.json)

此前的 [Qwen3／Jev 参数调控阶段清单](../../Qwen3_Jev_参数调控阶段清单.html)整理的是 Qwen3-0.6B 在 **Transformers 4.57.6 / PyTorch 2.6.0** 下的接口。它的数值范围、逐 token 钩子示例和实测标签只适用于当时的测试条件。现在本项目通过 Python `vllm.LLM.generate` 运行，每**一段**创建一次 `vllm.SamplingParams`。同名字段不等于行为、默认值、合法范围完全一致。

| 旧的 Transformers 概念 | 现在位于哪里 | 关键区别 |
|---|---|---|
| `model.generate(...)` | `backend.py` 中持久复用的 `vllm.LLM.generate(...)` | 不是 HTTP 补全请求，也不是 Transformers 的 `GenerationConfig`。 |
| `max_new_tokens` | 执行器计算的 `SamplingParams.max_tokens` | 每段根据段长、总 token 和上下文剩余空间重算；不能在 `parameters.json` 自行覆盖。 |
| `min_new_tokens` | 原生 `min_tokens`（当前代表子集未选） | 约束的是**单段**最少新 token，不能超过这一段的有效上限。 |
| `do_sample=False` | `temperature=0` 选择贪心生成 | 不向后端传 `do_sample` 字段。 |
| `temperature`、`top_p`、`top_k`、`repetition_penalty` | `SamplingParams` 的同名字段 | 须同时满足项目边界和所装 vLLM 的校验；不能直接继承旧清单的范围／默认值。 |
| `stop_strings` | `stop`，以及 `stop_token_ids`、`ignore_eos` | 停止匹配和结束原因以每一段为单位。 |
| `num_return_sequences` | 执行器固定要求一个候选 | `n`、`best_of` 由执行器保留，不能作为普通动态参数。 |
| 输出概率 | `logprobs`、`prompt_logprobs` | 这是 vLLM 生成记录；Jev 的四项 Score 是另外一套评价结果。 |
| LogitsProcessor、streamer、逐 token 回调 | 当前执行器没有相应钩子 | 控制器只在一段完成后观察，并修改下一次调用。 |
| 设备、精度、上下文、采样器选项 | `config.json` 的 `engine` / `runtime` | 创建引擎时设置，不能逐段热切换。 |
| `enable_thinking` | Qwen 分词器的聊天模板参数 | 在输入分词前选择，不是可直接设定的数字式思考预算。 |

`parameters.json` 当前选择 **20 个有代表性的原生 `SamplingParams` 字段**；写入列表就参与实验，删掉条目才排除。启动时检查定义；`doctor` 用初值调用所装 vLLM 的原生构造器；每段生成前还会校验当前值。控制器按类型为可调项生成 Jev Choice，缺少核实候选内容的字段只能保持。`api_name` 是 Python 原生参数名，不是 HTTP 请求字段。`initial: null` 是仍然传入的参数值，不等于排除这个字段。

旧 Transformers 测试不能证明 vLLM 在这个模型上也接受同样的值、更不能证明输出会受预期影响。`check` 只检查项目配置，`doctor` 检查初值的原生构造器接受情况，`smoke` 做短生成；实验记录能证明某值**已提交**到下一段。要证明实际输出效应，还需要受控对照。当前没有段内逐 token 热修改、Transformers 处理器链，也没有不调用 Jev 的连续生成基线。

`set`、`add`、`append`、`remove`、`update` 的类型示例见[中文参数教程](parameter_examples.zh-CN.md)。其中的示例 JSON 是教学数据，故意与当前运行规则有所不同。
