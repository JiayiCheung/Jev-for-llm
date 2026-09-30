# 参数定义：全部类型与操作

[English](parameter_examples.md) | **简体中文** | [当前实现](implementation.md) | [README](../README.zh-CN.md)

[完整示例列表](parameter_examples.json)使用互不重复的原生参数名，是独立教学文件，**不是当前生效配置，也不是建议一起启用的调优策略**。仍需通过本机 vLLM 和模型约束校验。只复制需要的完整条目到 `parameters.json`，替换同名或同 API 字段的旧条目，然后执行 `python run.py check` 和 `python run.py doctor`。

每项都有 `name`、`api_name`、`stage: completion`、`enabled`、`type`、`initial` 和 `adjustments`。下面片段展示变化部分，链接文件提供完整对象。触发名称仍只有 `narrow_sampling` 和 `reduce_repetition`。修改影响**下一段调用**，不会改写定义文件。`enabled: false` 的条目不会传入原生参数；`adjustments: {}` 则表示每段传同一个固定值。

## 当前项目真正启用的规则

真正运行的是 [parameters.json](../parameters.json)，下面的教学 JSON 不是当前配置。当前定义 **20 个已启用的原生 `SamplingParams` 字段**，其中只有三项配置了自动调整：

| 参数 | 初值 | 触发 → 操作 | 项目边界 |
|---|---:|---|---:|
| `temperature` | 0.6 | `narrow_sampling` → 减 0.1 | 0～2 |
| `top_p` | 0.95 | `narrow_sampling` → 减 0.05 | 0.01～1 |
| `repetition_penalty` | 1.0 | `reduce_repetition` → 加 0.05 | 1～1.5 |

Jev 的**原始 Score 分数**中，正确性 ≤ 2 或相关性 ≤ 2 会先触发 `narrow_sampling`；否则重复性 ≥ 2.5 才触发 `reduce_repetition`。待处理的回退、可选的评分停止、冷却期优先于这两个触发。0～4 的回退综合分与完整决策顺序见[当前实现](implementation.md)。这里用的是 **Score 评分题**，并不要求模型生成多个 Choice 候选。Jev 评价的是已生成的一整段，所以调整最早只能提交到下一次 `LLM.generate` 调用。此前的[Qwen3/Jev 参数阶段清单](../../Qwen3_Jev_参数调控阶段清单.html)基于 Transformers，不能当作 vLLM 的实测结论。

下面的示例特意把 `top_p` 设为固定值，但**当前运行配置**中的 `top_p` 可调整；示例 `stop`、`bad_words` 与 token ID 也只是占位演示。`minimum`/`maximum` 是本项目的策略边界，分别与原生构造器是否接受、模型能否正常运行、输出是否改变区分。`check` 校验文件结构和动作规则，`doctor` 用当前初值构造原生 `SamplingParams`；确认实际效果仍需模型生成实验。

## 1. Number：数值增减

```json
{
  "type": "number",
  "initial": 0.6,
  "minimum": 0,
  "maximum": 2,
  "adjustments": {
    "narrow_sampling": {
      "op": "add",
      "value": -0.1
    }
  }
}
```

用于 `temperature`，0.6 变成 0.5。已经为 0 时再减 0.1，仍限制为 0。number 接受整数与浮点数，不接受布尔值。

## 2. Integer：整数调整

```json
{
  "type": "integer",
  "initial": 20,
  "minimum": 1,
  "maximum": 100,
  "adjustments": {
    "narrow_sampling": {
      "op": "add",
      "value": -5
    }
  }
}
```

用于 `top_k`，20 变成 15。整数定义要求边界和增量也是整数；15.5 会被拒绝。

## 3. Boolean：设置开关

```json
{
  "type": "boolean",
  "initial": false,
  "adjustments": {
    "reduce_repetition": {
      "op": "set",
      "value": false
    }
  }
}
```

用于 `ignore_eos`，false 表示允许模型遇到 EOS 停止。`set` 直接赋值，字符串 `"false"` 不合法。这里 false → false 特意展示无变化操作；如果当前为 true，该规则会恢复 false。它只用于语法教学，不表示这样就能缓解重复。

## 4. String：替换停止标记

```json
{
  "type": "string",
  "initial": "END",
  "adjustments": {
    "narrow_sampling": {
      "op": "set",
      "value": "DONE"
    }
  }
}
```

用于 `stop`，下一次调用的停止标记从 END 换成 DONE。set 替换整个字符串，不是追加字符。停止标记可能截断有效答案，需要按任务选择。

## 5. Array：追加与删除元素

```json
{
  "type": "array",
  "initial": [
    "placeholder"
  ],
  "items": {
    "type": "string"
  },
  "adjustments": {
    "reduce_repetition": {
      "op": "append",
      "value": [
        "repeated phrase"
      ]
    },
    "narrow_sampling": {
      "op": "remove",
      "value": [
        "placeholder"
      ]
    }
  }
}
```

用于 `bad_words`，append 后为 `["placeholder", "repeated phrase"]`，再次追加相同元素不会重复。remove 删除匹配元素，对初值执行会得到 `[]`。即使只处理一个元素，动作 value 也必须是列表。每轮只选择一个触发原因，不会同时执行这两个分支。禁用词是语义限制，不保证对任务有利。

## 6. Object：浅层更新

```json
{
  "type": "object",
  "initial": {
    "42": -1
  },
  "additional_properties": {
    "type": "number",
    "minimum": -100,
    "maximum": 100
  },
  "adjustments": {
    "narrow_sampling": {
      "op": "update",
      "value": {
        "42": -2,
        "43": 1
      }
    }
  }
}
```

用于 `logit_bias`，更新后得到 `{"42": -2, "43": 1}`：已有键 42 改值，新键 43 加入，其他已有键保留。这是浅层合并，嵌套对象作为值时会整体替换；要换掉整个映射则使用 set。JSON 键是字符串；42 和 43 只是示例 token ID，真实实验前需检查分词器含义。

## 7. Null：显式关闭可选值

```json
{
  "type": "null",
  "initial": null,
  "adjustments": {}
}
```

用于 `prompt_logprobs`，传入 null 关闭提示词 log probability 采集。该定义只接受 null，改成整数会失败。null 与 `enabled: false` 不同：后者省略字段，让后端使用默认值。

## 8. 联合类型：在 null 与整数之间切换

```json
{
  "type": [
    "integer",
    "null"
  ],
  "initial": null,
  "minimum": 0,
  "maximum": 20,
  "adjustments": {
    "narrow_sampling": {
      "op": "set",
      "value": 5
    }
  }
}
```

用于 `logprobs`，null → 5 在下一次调用启用采集。set 可以在声明允许的类型之间切换；若改成 set null，就会关闭采集。数值边界只约束整数分支；可空数值定义不接受 add。对于可空列表或对象，也应先用 set 建立列表/对象，再执行 append/remove/update。

## 9. 启用但固定

```json
{
  "name": "top_p",
  "enabled": true,
  "initial": 0.95,
  "adjustments": {}
}
```

完整示例还包括数值类型和边界。该值每次都会传给 vLLM，但任何触发都不修改它，即使当前运行 adaptive 模式也保持固定。

## 10. 停用覆盖值

```json
{
  "name": "min_p",
  "enabled": false,
  "initial": 0,
  "adjustments": {}
}
```

定义仍保留供阅读，但不加入运行时值，也不传给原生接口，vLLM 使用自身默认值。这只是停用项目显式覆盖，不是关闭后端内部全部相关逻辑。

## 操作对照

| 操作 | value 形式 | 作用 |
|---|---|---|
| add | 数值增量 | 相加后限制在配置边界内 |
| set | 符合类型约束的值 | 完整替换 |
| append | 合法元素列表 | 在现有列表中追加未出现的元素 |
| remove | 合法元素列表 | 从现有列表中删除匹配元素 |
| update | 对象补丁 | 对现有对象做浅层合并 |

每次操作后都会校验结果。类型与边界说明可接受的数据，不代表方法有效，也不证明所有原生参数组合都受支持。
