# 当前实现：Qwen3 + Jev + 原生 vLLM

[English](implementation.md) · [中文总览](../README.zh-CN.md) · [参数示例](parameter_examples.zh-CN.md)

本文对应 `Code/` 内截至 2026-10-01 的代码和配置。较早的 [Qwen3／Jev 参数调控阶段清单](../../Qwen3_Jev_参数调控阶段清单.html)基于 Transformers 4.57.6；其中的逐 token 处理器、伪代码和测试状态不能直接当作这套 vLLM 程序的实现或验证。当前启用的原生参数以 `parameters.json` 为准。

## 谁控制什么、何时生效

| 层次 | 对应文件 | 生效时点 |
|---|---|---|
| 模型与引擎 | `config.json` 的 `engine`、`runtime`；`backend.py` | 创建 vLLM 引擎时；修改后要新建进程／引擎。 |
| 输入提示词 | `generation.enable_thinking`；`backend.py` 的 Qwen 聊天模板 | 每道题分词前；不是逐 token 的思考预算。 |
| 生成节奏 | `chunk_tokens`、`total_tokens`、`max_rounds`、`max_model_len`、`max_jev_calls`；`runner.py` | 每段生成前；按剩余预算决定 `max_tokens`。 |
| 采样与输出 | `parameters.json` 中 20 个已启用、`stage: completion` 的字段；`SamplingParams` | 每次 `LLM.generate` 前；不能在正在生成的一段中途改值。 |
| 评价 | `jev_questions.json`、`adapters.py`、`clients.py` | 每段生成非空结果后；一次 HTTPS 请求内含四道 Score 评分题。 |
| 决策 | `config.json` 的 `policy`；`policy.py` | 收到 Jev 结果后；提出的新参数最早在**下一段**提交。 |

`run.py` 把命令交给 `cli.py`。`PythonBackend` 在当前 Python 解释器里按需创建并复用一个 `vllm.LLM`，不需要本地 OpenAI 兼容服务，也没有可选后端或另行指定的 Python 路径。只有 Jev 使用网络请求。

## 一次题目／种子／模式的执行过程

1. 用 Qwen 聊天模板把题目转为 token。每次独立实验都从 `parameters.json` 的 `initial` 重新开始。
2. 每段请求的输入是**原提示词 token + 已生成的全部 token**；随机种子为初始种子加段号；`max_tokens` 取“每段上限、剩余总预算、剩余上下文容量”三者的最小值。程序要求只返回一个候选。提示词、`seed`、`max_tokens` 和候选数由执行器掌管，不能在参数定义文件里覆盖。
3. 后端用当前值创建新的原生 `SamplingParams`，调用 `LLM.generate`，取得 token ID、展示文本、结束原因及按需收集的 logprob。执行器另将累计 token ID 以 `skip_special_tokens=False` 解码为原始文本，送给 Jev，并写入 `answer.txt`。因此“展示用选项”和 Jev 看到的原始内容可能不同。
4. Jev 收到 `model`、四个 Score 量表和 `state = {task, generated, recent, step}`；标准答案不会发送，也不需要模型列出 Choice 候选。`parse_scores` 检查分数区间、概率等级键和概率总和。控制器实际使用的是**数值 Score**；概率会校验、记录，但当前不直接进入决策公式。
5. 控制器返回 `hold`、`adjust`、`rollback` 或 `stop`。执行器还会检查模型是否已停止以及各项预算；如果本轮已经结束，就不会执行所提议的下一轮参数。确认参数真的提交，须看**下一轮**的 `applied_parameters` 和 `generation_request`。

每一段都是新的生成调用，上一段的输出转成下一段的提示词。出现／频次惩罚针对当前调用的新生成 token，而重复惩罚还能看到转入提示词的历史 token；停止字符串未必跨段匹配。前缀缓存即使生效，也不能把分段调用等同于一次连续生成。

## 当前决策规则

四个维度是正确性、相关性、重复性、完整性，目前每个按 0～4 评分；**重复性越高越差**。触发和提前停止比较的是 Jev **原始分数**。现有 `config.json` 的判断顺序如下：

| 条件 | 结果 |
|---|---|
| `fixed` 模式 | 参数维持初值；每段仍调用 Jev。 |
| 上轮有参数调整，综合分下降**超过** `rollback.score_drop = 0.6` | 恢复调整前的参数，进入冷却；已生成文字不撤销。 |
| 开启 `stopping.enabled`，且完整性 ≥ 4、正确性 ≥ 3、相关性 ≥ 3 | 提议按评分停止。当前开关为 `false`；`compare` 也会在两组关闭它。 |
| 改值后尚处于 `cooldown_rounds = 1` 的冷却期 | 保持参数。 |
| 正确性 ≤ 2 **或**相关性 ≤ 2 | `narrow_sampling`：temperature 减 0.1、top_p 减 0.05，受项目边界限制。 |
| 否则重复性 ≥ 2.5 | `reduce_repetition`：repetition_penalty 加 0.05，受项目边界限制。 |
| 不满足触发，或动作做完没有实际改值 | 保持参数。 |

新触发之前先检查上轮调整的反馈；保留该调整之后也可能因冷却而暂不再改。综合分为 `4 × 加权平均(正确性/满分, 相关性/满分, 完整性/满分, 1 − 重复性/满分)`。当前五档量表和权重下，它等于 `0.45×正确性 + 0.30×相关性 + 0.15×完整性 + 0.10×(4−重复性)`，取值 0～4。这只是控制器定义的质量指标，**不是**标准答案正确率；相邻段分数变化也不能证明参数改变造成了变化。旧输出使用不同综合分尺度，不能直接比较。

当前 20 个启用字段中，只有 `temperature`、`top_p`、`repetition_penalty` 有非空自动调整规则。其他字段按初值传入。新增触发名称或调控阶段需要改代码，不能只在 JSON 中增添字段。

## 校验与结果

`check` 检查配置与题目，不加载 vLLM；`doctor` 用当前安装的 vLLM 构造初始 `SamplingParams`，但不加载模型；`smoke` 加载模型，最多生成 8 token，不调用 Jev；`run` 按配置模式执行；`compare` 对每道题和种子先跑 fixed 再跑 adaptive，两组都关闭评分提前停止，**两组仍调用 Jev**；`summarize` 只读既有结果，不判题。

每次实验增量保存 `outputs/<时间戳>_<模式>/result.json` 和 `answer.txt`。保存的配置会遮蔽 `jev.api_key`；记录包括请求、响应、耗时、评分、决策和 `decision_will_execute`。`status: completed` 只表示循环正常结束，不代表题做对。2026-09-30 的旧输出按先前策略产生，不能验证当前阈值或自动调整。程序尚无标准答案自动判分器，也没有“不调用 Jev 的连续生成”基线。
