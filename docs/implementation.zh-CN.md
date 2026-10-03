# 当前实现：Qwen3 + Jev + 原生 vLLM

[English](implementation.md) · [中文 README](README.zh-CN.md) · [参数示例](parameter_examples.zh-CN.md)

程序在 Python 中持有一个 `vllm.LLM` 实例，每段调用一次 `LLM.generate`。`engine` 和 `runtime` 在启动时生效；只有选中的 `SamplingParams` 能在下一段更改。题目提示词、种子、`max_tokens` 和单候选输出由运行器管理。

## 函数调用顺序

1. `config.load_config` 读取 `config.json`、`parameters.json` 和 `jev_questions.json`；`parameters.validate_parameters` 核对类型、边界与 `control` 元数据。
2. `backend.PythonBackend` 用 Qwen 聊天模板编码题目。每一段前，`runner.execute` 把已生成的 token ID 接回提示词，并按分段、总预算和上下文窗口计算本段 `max_tokens`。
3. `jev_requests.score_request` 生成四道 Score 的 JSON，`state={task, generated, recent, step}`。`adapters.parse_scores` 检查分数和概率分布并归一化到 0～1；重复性越高越差。
4. `policy.Controller.decide` 先处理 fixed 与回退判定。若还有下一段，adaptive 调用 `jev_requests.direction_request`，为每个当前可调字段构建符合其类型的 Choice。输入包含本轮 Score 和当前参数，不含标准答案或剩余 token 预算。
5. 如果所选动作需要具体值，`jev_requests.value_request` 再生成合法候选。数值方向给出 1、2、3 个步长的值；布尔切换等只有一个目标值时不再发第三次请求。`parse_choices` 检查所选选项及完整概率分布；`Controller.commit` 将改动留给下一段。
6. 下一轮的 `applied_parameters` 和 `generation_request` 才能证明改动真正传入 vLLM。`decision_will_execute=false` 表示实验先结束了。每轮的累计 `answer_snapshot` 也会按轮次写入 `answer.txt`。

fixed 每段最多一次 Jev 请求；adaptive 每段最多三次。请求数和轮数都没有上限，运行在模型自己停止或上下文窗口写满时结束。各阶段的请求和清理后的返回都存入 `result.json`；保存的配置遮蔽 `jev.api_key`。程序不使用或保存 Score/Choice 的 confidence 字段。

## 按类型给选项

`jev_requests.py` 根据声明类型构造动作，不靠参数名称写死。列表中每项都会进入原生请求；删掉条目才会排除，旧版参数级 `enabled` 会被拒绝。数值型给保持／增加／减少，再按 `control.window` 和 `control.denominator` 生成具体值；可空数值为 `null` 时从 `control.enable_candidates` 选择启用起点，已有数值时按相同步长增加／减少，并可关闭回到 `null`。布尔型给保持／切换；枚举在声明的 `choices` 中选。可空字符串、列表、映射只在适用时提供设置、添加、移除、清空。字符串和列表添加需要 `control.candidates`；映射添加需要核实过的 `control.entries`。候选为空时该字段只能保持。`control.adaptive=false` 使观测参数固定，但仍可作为原生参数传入。

当前 22 项是 [vLLM 完整清单分类](vllm_catalog_taxonomy.zh-CN.md)中的代表子集；清单出现不代表运行效果已经证实。按初值有 20 项可生成方向 Choice，只有 `stop_token_ids`、`allowed_token_ids` 要等核实过的 token 候选才可调。除数值、布尔和枚举外还有三类条目：带标签词组的 `logit_bias`、带核实预设的 `repetition_detection`、带候选词的 `bad_words`（见[参数指南](parameter_examples.zh-CN.md)）。其中有些属于观测或输出格式开关，不是答案质量旋钮。程序只实现当前的 `stage: completion` 路径。`doctor` 不加载模型，只用已安装的 vLLM 构造 `SamplingParams`。`output_kind` 字符串会先转换为原生 `RequestOutputKind`。

回退统计相邻片段加权归一化综合分的连续下降次数（不设幅度阈值），达到 `policy.revert.consecutive_declines` 次后恢复历史最优效用对应的参数；当前参数已经是它们时不回退。同一参数朝同一方向连续移动 `policy.limits.max_same_direction` 次后，不再提供该方向，直到它向相反方向移动；连续 `policy.dormancy.keep_streak` 次答 keep 的参数，接下来 `skip_rounds` 轮不再被提问。它不删除已生成文字，也不能证明某个参数造成分数变化；同轮改动多项尤其难归因。fixed 仍调用 Jev 保存 Score；compare 按题目和种子配对 fixed/adaptive。当前没有独立的标准答案判分器，`status: completed` 不等于答对。

## 从检查点重来

只要调用 Jev（fixed 和 adaptive，不含 baseline）并且 `policy.restart.enabled` 为真，一段很长的推理就可以被送回去重做。从第 `first_check_round`（20）轮起，Jev 回答一个 Choice：`continue`，或回到起点、任一更早的检查点。检查点是 Jev 被询问并回答 `continue` 的位置；回答 `continue` 后，下一次询问在 `recheck_every` 轮之后。

Jev 选了某个检查点后，其后的内容全部丢弃（在 `result.json` 里保留并标 `abandoned: true`），参数恢复为当时生效的值，用新种子（`seed + step + 1000 × 重来次数`）重新生成 `difference.probe_rounds` 轮。再用一个 Choice 请 Jev 判断这次新尝试与被放弃的是否换了方向；若判为 `same_approach` 则丢弃并重新生成，最多 `difference.max_tries` 次（用完后保留最后一次）。重来达到 `max_restarts` 次后不再询问。所有成本都记录：`total_generated_tokens` 统计每一次尝试，`wasted_tokens` 统计被丢弃的部分，`restarts[]` 记录选择、概率和判定。`generated_token_count` 与 `answer.txt` 只描述最终那次尝试。
