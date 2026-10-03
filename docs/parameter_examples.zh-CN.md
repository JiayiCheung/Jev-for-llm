# 类型化参数示例

[English](parameter_examples.md) · [当前生效定义](../parameters.json) · [严格 JSON 副本](parameter_examples.json)

`parameters.json` 的最外层是数组。下面三个代码块都是当前配置中的**完整参数条目**；可按需放入数组，用逗号隔开。`initial` 是初始值，`control` 定义允许的调整方式。修改后可运行 `python run.py doctor` 检查配置。

## 数值型：`temperature`

```json
{
  "name": "temperature",
  "api_name": "temperature",
  "stage": "completion",
  "type": "number",
  "initial": 0.6,
  "minimum": 0.2,
  "maximum": 2,
  "description": "Sampling randomness. Qwen3 advises against greedy decoding in thinking mode, so the window stops at 0.2.",
  "control": {
    "window": [0.2, 2],
    "denominator": 18
  }
}
```

当前值 `0.6` 可保持、增加或减少。步长为 `(2 − 0.2) ÷ 18 = 0.1`；温度下限 0.2 是刻意设置的（Qwen3 建议思考模式不要贪心解码），其余数值窗口都沿用 vLLM 自身的合法范围；选增加后，Jev 再从 `0.7`、`0.8`、`0.9` 中选具体值；选减少则从 `0.5`、`0.4`、`0.3` 中选。越界候选会被过滤。

## 布尔型：`ignore_eos`

```json
{
  "name": "ignore_eos",
  "api_name": "ignore_eos",
  "stage": "completion",
  "type": "boolean",
  "initial": false,
  "description": "Continue sampling after EOS; the experiment token cap still applies.",
  "control": {}
}
```

当前为 `false` 时，Jev 只需选择保持或打开；打开就得到 `true`，无需再选择数值。当前为 `true` 时，可保持或关闭。空的 `control` 不表示禁止调整。

## 可空整数：`logprobs`

```json
{
  "name": "logprobs",
  "api_name": "logprobs",
  "stage": "completion",
  "type": ["integer", "null"],
  "initial": null,
  "minimum": 0,
  "maximum": 20,
  "description": "Observation-only output log probabilities; not a quality control.",
  "control": {
    "enable_candidates": [0, 1, 2],
    "window": [0, 20],
    "denominator": 20
  }
}
```

`null` 表示当前未启用，但条目仍参与实验。若 Jev 选择启用，再从 `0`、`1`、`2` 中选择起点；当前值为 `1` 时，步长为 `1`，增加候选是 `2`、`3`、`4`，也可关闭回到 `null`。`logprobs` 用于观察输出概率，不是 Jev 评分或直接的答案质量控制。

## 其他类型

- **其他小数：**`top_p`（初值 0.95，窗口 `[0.05,1]`）、`repetition_penalty`（1.0，`[0.5,2]`，小于 1 会鼓励重复）、`frequency_penalty` 与 `presence_penalty`（0，`[-2,2]`）、`min_p`（0，`[0,1]`）各自使用配置中的窗口和分母。temperature、top_p、top_k、min_p 的初值取自 Qwen3 模型卡的思考模式推荐（0.6、0.95、20、0）。
- **整数：**`top_k=20`，实用窗口 `[1,201]`、分母 40，因此一步为 5；增加候选为 25、30、35。它另有单独的“关闭”动作，把值设为 0；再“启用”时回到 20。硬边界仍是 `[-1,1000000]`，不能拿一百万当作步长窗口。接近边界时删除越界或重复的候选。
- **可空列表：**`stop_token_ids` 和 `allowed_token_ids` 需要分词器核实过的整数 ID，后者不能设置为空列表。已有列表时可移除元素或清空。Jev 不能凭空写入列表元素。
- **可空映射：**`logit_bias=null` 要先填写核实过的 `control.entries`。每项是 `{token_id, value}`，或带标签的词组 `{label, group, token_ids, value}`。当前文件有 12 个词组条目：犹豫词（Wait、Hmm）与转折词（But、Alternatively、Actually、Maybe）各按 1、2、4、8 压低，思考结束符 `</think>` 按 4、8、12、16 抬高。所有 ID 都取自 Qwen3 分词器，且每个词是单个 token。Jev 选一个词组加一个强度；对同一词组选另一个强度是替换而不是叠加。数值问题里 Jev 看到的是标签而不是原始 ID。JSON 记录使用字符串键，后端在构造原生参数前转回整数 ID；已有映射时可整组删除（或删单个零散键）或清空。冒烟测试里 `</think>` 在 +0 到 +12 时 400 个 token 内都没有闭合，+16 时第 0 个 token 就闭合，所以只有高档位才是真正的“收尾”杠杆。
- **预设对象：**`repetition_detection=null` 提供 4 个核实过的预设（`control.presets`，每项含标签与取值，如 `{max_pattern_size: 30, min_pattern_size: 5, min_count: 3}`）。后端把字典转换为 vLLM 的 `RepetitionDetectionParams`。检测到循环时该段以 `repetition` 结束；运行把它当作普通的段结束并继续。
- **可空词表：**`bad_words` 硬性禁止某些词（`control.candidates`：Wait、Hmm、Alternatively、Actually、Maybe），每步加入一个。
- **枚举：**`output_kind` 初始为 `CUMULATIVE`，可切换到声明的另一个合法选项 `FINAL_ONLY`。后端把 JSON 字符串转换为 vLLM 原生枚举。
- **其他可空整数：**`prompt_logprobs` 遵循与 `logprobs` 相同的启用和步长规则，属于观测设置。
- **其他容易切换的字段：**`min_tokens` 只在 `0` 和 `1` 之间切换，确保只剩一个 token 生成空间时仍合法；`detokenize`、`skip_special_tokens`、`spaces_between_special_tokens`、`include_stop_str_in_output`、`flat_logprobs` 均为布尔开关。后几项改变观测或输出形式，依赖功能未启用时有的切换不会产生效果。

每次方向请求的上下文都包含当前 22 个值。目前 20 项有可执行方向；只有 `stop_token_ids` 和 `allowed_token_ids` 要先补经核实的 token 候选，暂时只能保持。技术上能修改，不等于适合用来纠正错误答案。

新增参数还须是已安装 `SamplingParams` 真正接受的字段；`python run.py doctor` 只构造参数，不加载模型、不调用 Jev。[完整清单](vllm_catalog_taxonomy.zh-CN.md)中的条件性功能或启动字段，要另外实现相应接口后才能进入这里。
