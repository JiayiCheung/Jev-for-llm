# Jev 与 vLLM 推理控制

[English](../README.md) | **简体中文** | [项目主页](https://jiayicheung.github.io/Jev-for-llm/)

Qwen 通过 **Python vLLM 接口在本地生成**；Jev 对每段输出做四个维度的 Score 评价；参数决策模块据此决定下一段使用的参数。一个进程内保持模型加载，只有 Jev 调用使用 HTTPS，**不需要启动本地 HTTP 服务**。

## 目录

- [1. 环境与安装](#1-环境与安装)
- [2. 目录与文件职责](#2-目录与文件职责)
- [3. 文件格式与配置](#3-文件格式与配置)
- [4. 函数调用与决策流程](#4-函数调用与决策流程)
- [5. 运行方式](#5-运行方式)
- [6. 首次运行与结果解读](#6-首次运行与结果解读)
- [7. 故障排查](#7-故障排查)
- [8. 实验边界与延伸阅读](#8-实验边界与延伸阅读)

## 1. 环境与安装

### 1.1 创建独立环境并获取仓库

先安装 Git、Conda 和适合显卡的 NVIDIA 驱动。在希望存放仓库的父目录打开终端：

```shell
conda create -n jev-vllm python=3.12 -y
conda activate jev-vllm
python -m pip install --upgrade pip
git clone https://github.com/JiayiCheung/Jev-for-llm.git
cd Jev-for-llm
```

后续命令均在包含 `run.py` 的仓库根目录执行。运行前按 1.4 节修改配置路径。已有可用 vLLM 环境的读者可直接激活原环境，跳过依赖重装。

### 1.2 安装 GPU 推理后端

本仓库不包含模型权重，其包元数据也不会自动安装 vLLM。在 Windows 上，阅读 [Windows 社区安装说明](https://github.com/SystemPanic/vllm-windows#installing-an-existing-release-wheel)，从[发布页](https://github.com/SystemPanic/vllm-windows/releases)下载与其声明的 Python、PyTorch、CUDA 要求匹配的 wheel，然后将下面文件名替换为实际下载文件：

```powershell
python -m pip install "C:/Downloads/ACTUAL_RELEASE_WHEEL.whl"
```

上述文件名是占位符，不是真实发布文件，不存在适合所有 Windows 环境的一条固定 wheel 命令。本实现曾使用 Python 3.12、Windows vLLM 0.29.0 构建验证，新环境仍需独立检查。

安装后检查解释器与 GPU：

```powershell
python -c "import sys, torch, vllm; print(sys.executable); print(vllm.__version__); print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())"
```

最后一行应为 `True`。这只证明 GPU 可见，不等于模型推理已经验证成功。

### 1.3 安装项目并下载模型

```shell
python -m pip install -e .
python -m pip install huggingface_hub
hf download Qwen/Qwen3-0.6B --local-dir models/Qwen3-0.6B
```

[Hugging Face CLI](https://huggingface.co/docs/huggingface_hub/guides/cli) 下载权重、分词器和配置。已有完整模型目录可跳过下载，直接配置路径。可编辑安装使包可导入，`run.py` 也支持直接从仓库运行。

### 1.4 修改本机路径和评价器配置

编辑 `config.json` 中已有的 `paths` 对象。按上面命令下载模型后，可使用以下片段：

```json
"paths": {
  "model": "models/Qwen3-0.6B",
  "dataset": "data/tasks.jsonl",
  "outputs": "outputs"
}
```

运行前激活环境，或显式使用对应的 Python 可执行文件。保留配置中的其他对象，并按第 3 节直接填写 `jev.api_key`，不需要额外输入凭据。

## 2. 目录与文件职责

```text
Jev-for-llm/
  run.py                 命令行入口
  config.json            路径、引擎、预算、API 密钥和决策阈值
  parameters.json        选中的原生参数、类型、初值和调整规则
  jev_questions.json     四个评分维度的英文指令与等级标准
  pyproject.toml         Python 包与构建元数据
  data/                  当前运行题目与抽样来源记录
  src/jev_vllm/          核心实现
  outputs/               实验输出
  README.md              项目说明
```

## 3. 文件格式与配置

| config.json 配置项 | 控制内容 |
|---|---|
| paths | 模型、题目文件、输出目录 |
| engine | LLM 构造参数：精度、上下文长度、序列容量、显存比例、eager 模式、张量并行 |
| runtime | 可选 FlashInfer 采样开关 |
| jev | HTTPS 地址、接口路径、模型、直接密钥、超时、评分标准文件 |
| generation | 思考开关、分段与总 token 预算、轮数上限 |
| parameters_file | 参数定义文件路径 |
| experiment | fixed/adaptive 模式、随机种子、每次实验的 Jev 调用上限 |
| policy | 冷却轮数、停止阈值、回退阈值、效用权重 |

项目固定使用当前 Python 解释器直接调用 vLLM。`engine` 在创建模型时生效；`parameters.json` 中的 SamplingParams 在下一次生成调用时生效。

### API 密钥直接放入配置

在已有的 `jev` 对象中填写：

```json
"api_key": "YOUR_TYPESAFE_API_KEY"
```

程序直接读取 `jev.api_key`，**不需要设置环境变量，也不会要求交互输入密钥**。真实密钥保存在本地配置；发布该文件前将其替换为占位符。保存到实验结果中的配置会遮蔽 `api_key`。

接口地址为 `https://api.typesafe.ai/v1/systemone`，使用 Bearer 认证。本实现用 Python 标准库发送请求，不需要另装 TypeSafe SDK。参见 [TypeSafe API quickstart](https://docs.typesafe.ai/introduction/quickstart)。

### 参数定义与运行时数值

`parameters.json` 最外层是一个列表，每项定义一个参数。例如：

```json
{
  "name": "temperature",
  "api_name": "temperature",
  "stage": "completion",
  "type": "number",
  "initial": 0.6,
  "minimum": 0,
  "maximum": 2,
  "description": "Sampling randomness",
  "control": {"window": [0, 2], "denominator": 20}
}
```

| 字段 | 含义 |
|---|---|
| name | 控制器内部的参数名称 |
| api_name | 传给原生 SamplingParams 的关键字 |
| stage | 本项目当前只实现 completion |
| type | 数值、整数、布尔、字符串、列表、对象、null 或这些类型的联合 |
| initial | 每个题目/种子/模式实验开始时的数值 |
| minimum / maximum | 项目设定的边界，不代表 vLLM 全部合法范围 |
| control | 按类型生成 Jev Choice 的元数据；数值参数用 window/denominator |

读取文件后，`initial_parameters` 从每个条目只取 `name` 和 `initial`，形成一张普通的运行时映射。例如 `temperature`、`ignore_eos`、`logprobs` 三项得到 `{"temperature": 0.6, "ignore_eos": false, "logprobs": null}`；实际映射包含列出的全部 20 项。类型、说明、边界和 `control` 仍保留在参数定义中，供校验及后续生成 Jev Choice 使用，不会嵌套进每个运行时值。这张映射先保存在内存中的 `sampling`，每次独立实验从它复制初值；每轮实际使用的参数另记在 `result.json` 中。

当前解析器要求每项都写 `control`，即使没有额外设置也要写 `"control": {}`。布尔型 `ignore_eos` 和枚举型 `output_kind` 仅凭类型、当前值及声明的 `choices` 就能生成动作；**空对象不表示禁止调整**。如果希望某项仍传给 vLLM、但始终保持初值，写 `"control": {"adaptive": false}`。数值型须提供 `window`、`denominator`；可空数值型还须提供 `enable_candidates`；列表和映射要先提供核实过的 `candidates` 或 `entries`，才能新增内容。

若 Jev 为 temperature 选 `increase`，程序会按窗口跨度除以 20 生成 0.7、0.8、0.9 等合法候选，再请 Jev 选具体值。**运行时调整不会改写 `initial`**；下一次独立实验仍从 0.6 开始。

列表可用 `items` 约束元素；对象可用 `properties`、`required`、`additional_properties` 约束内容。布尔参数只有保持或切换；枚举只能选声明的 `choices`；字符串、列表、映射必须先在 `control.candidates` 或 `control.entries` 中填写核实过的内容，程序才会提供设置、增删等动作。

各类代表参数及候选内容规则见[参数示例教程](parameter_examples.zh-CN.md)。[严格 JSON 示例](parameter_examples.json)是当前选择去除注释后的副本。

更完整的 vLLM 范围见 [1,181 项清单分类](vllm_catalog_taxonomy.zh-CN.md)及其[逐条 CSV](vllm_catalog_taxonomy.csv)。这份清单区分了当前 Python 控制项与其他接口，并不代表所有项目已经通过运行验证。

### Jev 评分标准与输入题目

`jev_questions.json` 定义四个固定名称的 Score 维度：

| 维度 | 评价对象 | 高分含义 |
|---|---|---|
| correctness | 已生成内容的正确性；未完成本身不算错误 | 更正确 |
| relevance | 是否围绕题目展开 | 更相关 |
| repetition | 最近片段结合历史是否无效重复 | 重复更严重，越低越好 |
| completeness | 是否给出覆盖题目的完整最终答案 | 更完整 |

每个维度有 `type: score`、英文 `instructions`、有序 `criteria` 列表。当前五档索引为 0–4；归一化分数为原始分数除以 4。修改等级数量后，适配器使用新的最大索引归一化。

模型要解答的题目在 `data/tasks.jsonl`，**不在评分标准文件里**。JSONL 每行是一个完整的严格 JSON 对象，不支持注释，也没有外围数组：

```jsonl
{"id":"example_001","prompt":"Solve 2x + 3 = 11.","reference_answer":"4"}
```

`id` 必须是唯一非空字符串，`prompt` 必须是非空字符串。参考答案是可选元数据，不发送给 Qwen/Jev。仓库附带的样本是 GSM8K **训练集**英文原题，使用随机种子 42 无放回抽取 10 道；抽样记录在 `data/gsm8k_sample_manifest.json`。这不是完整的独立测试集评测，当前也没有自动比对标准答案的判分器。

## 4. 函数调用与决策流程

| 模块 | 职责 |
|---|---|
| run.py / cli.py | 解析命令、选择模式、建立共享客户端、遍历题目和种子 |
| config.py | 去除注释、解析路径、加载参数和评分标准、检查配置 |
| parameters.py / value_schema.py | 初值与类型校验、映射原生参数名 |
| backend.py | 保持模型加载，分词、生成、解码 |
| runner.py | 分段循环、预算、评价调用、增量保存记录 |
| jev_requests.py | 分别构造 Score、方向 Choice、具体值 Choice 的 JSON |
| adapters.py | 校验 Score、归一化并清理不使用的返回字段 |
| clients.py | 发送带认证的 HTTPS 请求 |
| policy.py | 评分停止、冷却、回退和提交 Jev 已选的参数 |


对一道题、一个种子、一种模式，实际调用顺序如下：

1. **读取定义并映射初值。**`config.load_config` 读取 `parameters.json` 和 `jev_questions.json`。`parameters.initial_parameters` 从列出的每项取 `name` 与 `initial`，组成普通的内存映射 `sampling`；`type`、`description`、边界和 `control` 仍留在定义中，供校验和后续 Choice 使用。每次独立实验复制这张初始映射。程序不单独写出“初始映射文件”，后续改参也不改写文件里的 `initial`。
2. **用初值生成第一段。**`runner.execute` 将题目文件中的 `prompt` 套用模型聊天模板，得到提示词 token ID；`add_generation_prompt` 只添加助手开始回答的标记，不会另造一道题。每轮生成请求包含这些 token 加此前已生成的 token、按 `api_name` 转换后的当前参数、由剩余预算限制的本段 `max_tokens`，以及 `seed + step`。调用前在 `result.json` 记 `rounds[].applied_parameters`、`generation_request`；成功返回后记 `generation_response` 和耗时。第一段生成前，Jev 尚未改过参数。
3. **给新文字评分。**新 token 接到累计输出后，`jev_requests.score_request` 发送四项 Score，`state={task, generated, recent, step}` 分别是原题、累计全文、最新片段和轮次；不发送参考答案或剩余 token 预算。调用前保存 `evaluation_request`，返回后保存 `evaluation_response` 与耗时。`adapters.parse_scores` 要求分数处于量表范围且有限、概率键覆盖每一档、概率之和与 1 的偏差不超过 0.02；再按当前五档量表把原始 0～4 分映射为 `normalized=score/4`，例如 3 分变 0.75。概率分布会保存、校验；控制器使用归一化分数，不使用额外的 confidence。整理结果在 `rounds[].scores`。
4. **判断是否允许调参。**`policy.Controller.decide` 将四项归一化分数合成 `utility`，计算时把重复性反向处理，因为重复越少越好。fixed 模式保持原参数；adaptive 先检查上次改参是否应回退，再检查可选的评分停止和冷却。运行器还检查模型是否停止，以及 token、上下文、轮数、Jev 调用预算。只有还能继续且得到 `reason: choice_ready`，才进入参数 Choice。这一步只是本地判断，不会改变刚完成的生成。
5. **生成并发送方向 Choice。**`jev_requests.direction_request` 逐项读取类型和当前值，建立合法动作。例如 `temperature=0.6` 是 `keep/increase/decrease`，`ignore_eos=false` 是 `keep/turn_on`，`logprobs=null` 是 `keep/enable`。若某项只有 `keep`，就不建问题；按目前初值，20 项中有 17 项形成问题，另 3 项缺少核实过的 token ID 候选。这 17 道题放进**同一次 Jev 请求**，共享原题、生成文字、四项归一化分数和全部当前参数；每题另带该参数的 `description` 与当前值。请求和答复保存为 `direction_request`、`direction_response`。这里是逐参数选择动作，代码没有对整组改动做联合优化。
6. **把方向映射为具体值。**选 `keep` 不改值；`turn_on` 之类只有一个结果的动作直接映射为 `true`。数值增减由 `jev_requests.value_candidates` 按 `control.window` 跨度除以 `denominator` 算步长，展示 1、2、3 步，并剔除越过窗口或硬边界的值。例如 `temperature=0.6`、窗口 `[0,2]`、分母 20，增加得到 `0.7/0.8/0.9`；`top_k=20`、窗口 `[1,101]`、分母 20，增加得到 `25/30/35`。`logprobs=null` 若选启用，先从声明的 `0/1/2` 中选起点，已有整数后才能按步长增减。多个具体候选的参数被合并到**一次额外的 Jev 请求**，记录为 `value_request`、`value_response`、`value_seconds`；返回的 `v1/v2/v3` 再映射回实际值。请求附带当前参数和各题自身的方向，但共同 `state` 没有汇总其他参数刚选的方向。
7. **提交给下一段。**`Controller.commit` 复制完整的当前参数映射，再用选中的 `changes` 覆盖对应项。没有实质变化就保持；有变化则在 `rounds[].decision` 写入 `action: adjust`、完整的下一段参数及改前综合分，以备反馈比较。运行器把新映射复制给下一轮。`decision_will_execute: true` 只表示打算继续；须看下一轮的 `applied_parameters`、`generation_request`，才能知道新值被提交给 vLLM，再看 `generation_response` 才能确认该次生成完成。下一轮开始前也可能先被预算拦住。
8. **保存各轮答案并检查效果。**程序持续更新 `result.json`；每轮的 `answer_snapshot` 和 `answer.txt` 中带轮次标题的段落保存该轮结束时的累计答案，最后一段是完整最终答案。下一轮评分后，控制器把新的 `utility` 与改参前的值比较；若下降超过 `policy.rollback.score_drop`，会提议在后续轮次恢复旧参数，但不会抹掉已经生成的文字。旧版“低正确性／高重复性就固定调整”的触发规则已删除。

评分提前停止仍由 `policy.stopping` 中的 0～1 归一化门槛控制，当前 `enabled: false`，所以这些门槛不触发停止。

综合质量分取值为 0～1。当前五档评分与默认权重下，计算为 `0.45*(correctness/4) + 0.30*(relevance/4) + 0.15*(completeness/4) + 0.10*(1-repetition/4)`。`utility_weights` 全部填写非负数（0～1，至少一项大于零），代码自动除以权重之和；评分档数变化时会按对应满分归一化。`policy.rollback.score_drop: 0.15` 表示调整后综合分下降超过 0.15 就恢复原参数，不是下降 15%。这保留了原来的默认回退敏感度。回退不删除已生成文本，也不能证明因果关系。旧结果的效用数值采用旧尺度，不能与新结果直接比较。

## 5. 运行方式

在包含 `run.py` 的目录中由使用者自行执行：

| 命令 | 用途 | 加载 GPU 模型 | 调用 Jev |
|---|---|---|---|
| `python run.py check` | 检查配置和题目加载 | 否 | 否 |
| `python run.py preview` | 打印三阶段示例 JSON，检查 Jev 输入形状 | 否 | 否 |
| `python run.py doctor` | 构造原生 SamplingParams 校验 | 否 | 否 |
| `python run.py smoke` | 第一题实际生成 8 个 token | 是 | 否 |
| `python run.py run` | 运行配置指定的 fixed 或 adaptive | 是 | 是 |
| `python run.py compare` | 每题/种子先 fixed 再 adaptive | 是 | 是 |
| `python run.py summarize` | 列出保存的实验摘要 | 否 | 否 |

使用另一份配置：

```powershell
python run.py run --config "E:\Experiments\config.json"
```

同时应复制它引用的文件，或修改引用路径。`run` 根据 `experiment.mode` 选择模式；`compare` 自动跑两种模式，并在两组关闭评分触发的提前停止。**fixed 组仍调用 Jev 记录评分，只是不根据评分调整参数**。当前尚未实现“连续生成且完全不调用 Jev”的第三组基线。

Jev 请求数上限为：

```text
题目数 × 种子数 × 各模式的 min(max_jev_calls, max_rounds × 每轮最多请求数)
```

fixed 每轮最多 1 次 Score；adaptive 每轮最多 1 次 Score、1 次方向 Choice、1 次具体值 Choice。10 道题、1 个种子、最多 8 轮时，fixed 上限 80 次、adaptive 上限 240 次、compare 合计上限 320 次，实际还受 `max_jev_calls`（每个实验目录的上限）约束。模型停止、所有参数保持等情况会减少请求。

### 七个命令分别怎么用

先激活环境，再在仓库根目录运行。执行检查不会自动启动实验。

**check：检查配置与题目**

```shell
python run.py check
```

预期输出以 `Configuration valid; tasks=...; backend=python; mode=...` 开头。它读取主配置、参数定义、评分标准和题目，不加载模型，不验证密钥认证，也不消耗 Jev 额度。

**preview：离线查看三阶段 Jev JSON**

```shell
python run.py preview
```

使用第一道题和示例评分打印 Score、方向 Choice、具体值 Choice 的 JSON；不加载 Qwen，也不调用 Jev。

**doctor：校验原生参数接口**

```shell
python run.py doctor
```

预期输出为 `Native SamplingParams validated. No model loaded and no Jev call made.`。它导入 vLLM 并用选定值构造 SamplingParams，不执行 GPU 推理，也不能证明后续所有参数组合都可用。

**smoke：短小的本地生成检查**

```shell
python run.py smoke
```

加载 Qwen，对第一题生成最多 8 个 token，在终端打印响应 JSON。不调用 Jev，也不创建正常实验结果目录。只得到短片段是正常情况，这不是答案质量测试。

**run：运行配置中的一种模式**

```shell
python run.py run
```

按照 `experiment.mode` 遍历全部题目和种子，调用 Jev，并为每个题目/种子保存结果目录。下面提供 fixed 和 adaptive 两种配置例子。

**compare：每题每种子运行两组**

```shell
python run.py compare
```

命令覆盖配置中的模式，每个题目/种子先 fixed 再 adaptive，两组都关闭评分触发的停止。它生成独立结果目录，不生成统计比较报告。两组都调用 Jev；adaptive 每轮还可能增加两次 Choice 请求，因此开销要按实际请求数和生成长度核算。

**summarize：读取已有结果**

```shell
python run.py summarize
```

每个结果输出一条 JSON 摘要，包括题目、种子、模式、状态、停止原因、生成 token 数、Jev 调用数、耗时和路径。不调用模型或 API，但仍会加载当前配置和题目，因此这些文件需保持有效。只查找 outputs 直接子目录内的结果，不执行答案判分。

### fixed / adaptive / compare 三种实验操作

以下片段替换 `config.json` 已有的 `experiment` 对象，保留其他部分。

**A. 固定参数，Jev 只负责观察评分**

```json
"experiment": {
  "mode": "fixed",
  "seeds": [42],
  "max_jev_calls": 8
}
```

```shell
python run.py run
```

每段都评分，参数始终使用初值。结果目录以 `_fixed` 结尾，决策保持不变，原因可能为 `fixed_parameter_control`。10 道题、最多 8 轮时，请求上限为 80 次。

**B. 根据 Jev 反馈自适应调参**

```json
"experiment": {
  "mode": "adaptive",
  "seeds": [42],
  "max_jev_calls": 8
}
```

```shell
python run.py run
```

结果目录以 `_adaptive` 结尾，可能保持、调整、回退；若启用了评分停止，还可能据此结束。保持参数也是有效结果。10 道题、8 轮的请求上限为 240 次，还受各次运行的 `max_jev_calls` 限制。

**C. 固定／自适应配对实验**

保留以上任一配置，命令自动选择两组：

```shell
python run.py compare
```

10 道题、1 个种子，最多生成 20 个实验目录，8 轮时最多 320 次请求，还受各次运行的 `max_jev_calls` 限制。两组初值与预算一致，但 EOS 与预算停止仍有效，所以实际长度可能不同。分别查看 result.json 和 answer.txt；比较正确率仍需要独立标准答案判分器。

## 6. 首次运行与结果解读

1. 修改路径、`jev.api_key` 和题目文件。
2. 依次执行 `check`、`doctor`、`smoke`。
3. 根据实验目标选择 **run 或 compare 其中一个**。
4. 执行 `summarize` 并查看保存记录。

配置好仓库与密钥后，单模式实验执行：

```powershell
conda activate jev-vllm
cd Jev-for-llm
python run.py run
```

如果要跑两组对照，将最后一条换成 `python run.py compare` 即可，不需要在 config.json 之外配置密钥。`check` 不会验证 API 密钥是否能通过认证；`doctor` 只验证参数构造，不能证明模型和所有参数组合实际运行成功。

每个题目/种子/模式生成一个 `outputs/<timestamp>_<mode>/`，包含 `result.json` 和 `answer.txt`。`answer.txt` 按轮次列出每轮结束时的**累计答案快照**；最后一段就是最终完整答案。`result.json` 的每轮还保留 `answer_snapshot`。重点查看每轮 `rounds[]` 的 `scores`、`decision`、`applied_parameters`、`generation_request`、耗时以及最终停止原因。

决策只是对下一段的提议，**下一轮实际请求才证明新参数被使用**。`decision_will_execute` 也不能单独证明下一次调用已成功。

`completed` 表示循环正常结束，不代表答案正确。结束可能源于模型、token/上下文/轮数/调用预算，或启用的评分停止。Ctrl+C 通常会保存 interrupted 状态；强制结束进程可能留下 running 状态。程序保留部分记录。中断后可用 `python run.py compare --start-task 题目ID` 从该题开始继续整批，但该题会重新开始，不能接续到中断的段；先前结果目录不会被覆盖。Jev 临时 HTTP 5xx 错误最多额外重试两次，仍失败就停止后续实验。

配置好密钥后，可将控制台输出存到本地已有日志目录：

```powershell
New-Item -ItemType Directory -Force outputs | Out-Null
python run.py compare 2>&1 | Tee-Object -FilePath outputs/compare.log
```

此 PowerShell 示例将控制台日志保存在仓库的 outputs 目录。日志可能含题目和生成内容，完整实验依据应以保存结果为准。

## 7. 故障排查

| 现象 | 检查方向 |
|---|---|
| 仍提示输入密钥 | 旧进程或旧代码；停止后使用更新后的代码重启，当前只读 jev.api_key |
| HTTP 401/403 | 密钥是否有效、组织权限是否正常 |
| Billing / out of funds | TypeSafe 组织余额 |
| 超时或 TLS 错误 | 网络、代理、超时设置；当前不自动重试 |
| 无法 import vllm | 当前解释器环境与所安装 wheel |
| 显存不足 | 其他 GPU 进程、上下文长度、引擎显存设置 |
| 自行新增 min_tokens 后报错 | 是否超过当轮实际剩余预算；smoke 只分配 8 个 token |
| 预算用完仍无最终答案 | 检查 thinking 输出，按需要有意识地提高预算 |

## 8. 实验边界与延伸阅读

每段都是独立的 generate 调用，历史 token 作为下一段提示词。presence/frequency penalty 的计数针对本次调用新生成 token；repetition penalty 还考虑提示词。跨片段的停止字符串匹配不作保证。参数在调用之间改变，不是在正在执行的生成内部热修改。前缀缓存可能减少重复计算，但不会使分段生成等同于一次连续生成。

Jev 和 `answer.txt` 的各轮快照使用累积 token 的原始解码，可能保留特殊 token 和停止内容；显示参数作用于原生显示文本。每段使用 `seed + step`。fixed/adaptive 共享初始值和预算，不保证随机轨迹相同，也不保证准确率提高。

更多信息见[实现说明](implementation.zh-CN.md)、[Transformers 迁移说明](transformers_to_vllm.zh-CN.md)和 [GSM8K 来源](https://github.com/openai/grade-school-math)。报告 benchmark 正确率前，应增加独立的答案判分器。
