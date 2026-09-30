# Jev 与 vLLM 推理控制

[English](README.md) | **简体中文**

Qwen 通过 **Python vLLM 接口在本地生成**；Jev 对每段输出做四个维度的 Score 评价；参数决策模块据此决定下一段使用的参数。一个进程内保持模型加载，只有 Jev 调用使用 HTTPS，**不需要启动本地 HTTP 服务**。

## 目录

- [1. 环境与安装](#1-环境与安装)
- [2. 目录与文件职责](#2-目录与文件职责)
- [3. 文件格式与配置](#3-文件格式与配置)
- [4. 函数调用与决策流程](#4-函数调用与决策流程)
- [5. 运行方式](#5-运行方式)
- [6. 首次运行与结果解读](#6-首次运行与结果解读)
- [7. 测试与故障排查](#7-测试与故障排查)
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

后续命令均在包含 `run.py` 的仓库根目录执行。仓库配置含原工作站路径，**克隆后必须先按 1.4 修改路径**。已有可用 vLLM 环境的读者可直接激活原环境，跳过依赖重装。

### 1.2 安装 GPU 推理后端

根据平台选择**一条路线**。本仓库不包含模型权重，其包元数据也不会自动安装 vLLM。

**Linux / WSL2 + NVIDIA GPU：**在 Linux 环境内安装上游默认 wheel 及配套依赖：

```shell
python -m pip install vllm
python -m pip check
```

这是默认 wheel 安装路线，不是固定版本的环境锁。安装前按[官方 GPU 安装要求](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/)检查 Python、GPU 和驱动；其他 CUDA/PyTorch 组合可能需要选择不同构建。WSL 命令在 Linux 内执行，不是在 Windows Conda 环境执行。

**原生 Windows：**阅读 [Windows 社区安装说明](https://github.com/SystemPanic/vllm-windows#installing-an-existing-release-wheel)，从[发布页](https://github.com/SystemPanic/vllm-windows/releases)下载与其声明的 Python、PyTorch、CUDA 要求匹配的 wheel，然后将下面文件名替换为实际下载文件：

```powershell
python -m pip install "C:/Downloads/ACTUAL_RELEASE_WHEEL.whl"
python -m pip check
```

上述文件名是占位符，不是真实发布文件，不存在适合所有 Windows 环境的一条固定 wheel 命令。本实现曾使用 Python 3.12、Windows vLLM 0.29.0 构建验证，新环境仍需独立检查。

两条路线安装后都检查解释器与 GPU：

```shell
python -c "import sys, torch, vllm; print(sys.executable); print(vllm.__version__); print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())"
```

最后一行应为 `True`。这只证明 GPU 可见，不等于模型推理已经验证成功。

### 1.3 安装项目并下载模型

```shell
python -m pip install -e .
python -m pip install huggingface_hub
hf download Qwen/Qwen3-0.6B --local-dir models/Qwen3-0.6B
```

[Hugging Face CLI](https://huggingface.co/docs/huggingface_hub/guides/cli) 下载权重、分词器和配置。已有完整模型目录可跳过下载，直接配置路径。`pyproject.toml` 描述 Python 包，不是 GPU 依赖锁文件；可编辑安装使包可导入，`run.py` 也支持直接从仓库运行。

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

NVIDIA 驱动、PyTorch CUDA runtime、CUDA Toolkit 是不同层次。可选 JIT 内核还可能需要 Toolkit 和兼容编译器。第一次运行保持 `runtime.use_flashinfer_sampler` 为 false。Windows JIT 编译可能需要正确初始化的 MSVC 开发者终端；安装 VS Code C/C++ 扩展不会安装 `cl.exe`。

## 2. 目录与文件职责

```text
Jev-for-llm/
  run.py                 命令行入口
  config.json            路径、引擎、预算、API 密钥和决策阈值
  parameters.json        选中的原生参数、类型、初值和调整规则
  jev_questions.json     四个评分维度的英文指令与等级标准
  pyproject.toml         Python 包与构建元数据
  data/                  当前运行题目与抽样来源记录
  docs/                  实现说明与迁移说明
  src/jev_vllm/          核心实现
  outputs/               实验输出
  README.md              英文说明
  README.zh-CN.md         中文说明
```

开发工作区还在仓库外使用 `../tests`、`../scripts`、`../data` 分别保存控制器测试、辅助脚本/日志、原始下载。这些目录不属于仓库，也不是正常运行的前提。单独克隆时可能不存在；实际使用的题目是仓库内 `data/tasks.jsonl`。vLLM 原生接口测试另行维护。

## 3. 文件格式与配置

三个配置文件采用 **JSON 结构加自定义 `#` 行注释**。字符串用双引号，布尔值写 `true`/`false`，可选空值写 `null`。不支持尾随逗号、`//` 注释或块注释。普通 `json.load` 无法直接读取带注释内容；项目使用 `load_config` 处理。VS Code 将文件关联为 YAML 只是为了显示高亮，**不代表可以使用普通 YAML 语法**。

代码、配置注释和发送给模型的提示词保持英文；中文只用于这份说明。相对路径以配置文件所在目录为基准。JSON 中 Windows 路径要写转义反斜杠，例如 `"E:\\Models\\Qwen3-0.6B"`，也可以使用正斜杠。

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
  "enabled": true,
  "type": "number",
  "initial": 0.6,
  "minimum": 0,
  "maximum": 2,
  "adjustments": {
    "narrow_sampling": {"op": "add", "value": -0.1}
  }
}
```

| 字段 | 含义 |
|---|---|
| name | 控制器内部的参数名称 |
| api_name | 传给原生 SamplingParams 的关键字 |
| stage | 本项目当前只实现 completion |
| enabled | 是否传入这个参数覆盖值 |
| type | 数值、整数、布尔、字符串、列表、对象、null 或这些类型的联合 |
| initial | 每个题目/种子/模式实验开始时的数值 |
| minimum / maximum | 项目设定的边界，不代表 vLLM 全部合法范围 |
| adjustments | 触发原因对应的调整动作；空对象表示保持固定 |

例如触发 `narrow_sampling` 后，运行时 temperature 从 0.6 变为 0.5，**不会把 parameters.json 的 initial 改写成 0.5**。下一次独立实验仍从 0.6 开始。

列表可用 `items` 约束元素；对象可用 `properties`、`required`、`additional_properties` 约束内容。支持 `add`、`set`、`append`、`remove`、浅层 `update` 五类动作；数值加法会限制在配置边界内。`append/remove` 要求当前值是列表，`update` 要求当前值是对象；当前为 null 时先用 `set`。

目前实现的触发名称只有 `narrow_sampling` 和 `reduce_repetition`。增加新的触发名称还需要修改策略与校验代码，不能只在定义文件里写一个新名称。

当前选择了以下 20 个原生字段。安装的 vLLM 还会进一步检查自身限制与参数组合。

| 参数 | 类型 | 初值 | 项目边界或含义 |
|---|---|---|---|
| temperature | number | 0.6 | 0–2；0 为贪心解码 |
| top_p | number | 0.95 | 0.01–1 |
| top_k | integer | 20 | −1–1,000,000；具体合法值还需原生校验 |
| repetition_penalty | number | 1 | 1–1.5 |
| min_p | number | 0 | 0–1 |
| presence_penalty | number | 0 | −2–2 |
| frequency_penalty | number | 0 | −2–2 |
| stop | string / array / null | null | 字符串或字符串列表 |
| stop_token_ids | array / null | null | 非负整数 token ID 列表 |
| ignore_eos | boolean | false | 是否忽略 EOS |
| min_tokens | integer | 0 | 0–1024；还必须小于等于每段实际剩余预算 |
| logprobs | integer / null | null | 0–20；null 关闭采集 |
| prompt_logprobs | integer / null | null | 0–20；null 关闭采集 |
| detokenize | boolean | true | 原生显示文本 |
| skip_special_tokens | boolean | true | 原生显示文本 |
| spaces_between_special_tokens | boolean | true | 原生显示文本 |
| include_stop_str_in_output | boolean | false | 原生显示文本 |
| bad_words | array / null | null | 禁用词字符串列表 |
| allowed_token_ids | array / null | null | 非负整数 ID；关闭限制用 null，不用空列表 |
| logit_bias | object / null | null | token ID 字符串映射到 −100–100 数值偏移 |

目前只有 temperature、top_p、repetition_penalty 配置了自动调整动作。添加其他字段前，要确认已安装 SamplingParams 和当前分段流程支持它；添加一个名称不会自动实现对应适配逻辑。seed、max_tokens 和单候选输出由运行器管理。

全部类型与操作的逐项例子，包括固定值和停用条目，见[参数示例教程](docs/parameter_examples.zh-CN.md)。[完整示例 JSON](docs/parameter_examples.json)独立于当前生效配置。

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

`id` 必须是唯一非空字符串，`prompt` 必须是非空字符串。参考答案是可选元数据，不发送给 Qwen/Jev。当前开发样本是 GSM8K **训练集**英文原题，使用随机种子 42 无放回抽取 10 道；抽样记录在 `data/gsm8k_sample_manifest.json`。这不是完整的独立测试集评测，当前也没有自动比对标准答案的判分器。

## 4. 函数调用与决策流程

| 模块 | 职责 |
|---|---|
| run.py / cli.py | 解析命令、选择模式、建立共享客户端、遍历题目和种子 |
| config.py | 去除注释、解析路径、加载参数和评分标准、检查配置 |
| parameters.py / value_schema.py | 初值、类型与动作校验、映射原生参数名 |
| backend.py | 保持模型加载，分词、生成、解码 |
| runner.py | 分段循环、预算、评价调用、增量保存记录 |
| adapters.py | 构造 Jev 输入、校验返回格式、归一化 |
| clients.py | 发送带认证的 HTTPS 请求 |
| policy.py | 触发选择、冷却与参数回退 |


`build_evaluation` 发送 `model`、`questions` 和 `state`。state 包含题目 `task`、累积生成文本 `generated`、最近片段 `recent`、从 0 开始的 `step`。不会发送参考答案。

`parse_scores` 要求每个维度返回 Score 类型，分数在量表范围内且有限，概率键覆盖所有等级，概率和与 1 的偏差不超过 0.02。五档量表中的 3 分会成为 0.75。

当前默认决策顺序：

1. fixed 模式：保持参数。
2. 上轮调整后的综合质量分下降超过 0.6 分：回退参数。
3. 若启用了评分停止，检查完整度、正确性和相关性阈值。
4. 冷却期间：保持参数。
5. 正确性原始分数不高于 `correctness_max`，或相关性原始分数不高于 `relevance_max`：temperature 减 0.1，top_p 减 0.05。
6. 否则若重复性原始分数不低于 `repetition_min`：repetition_penalty 加 0.05。

直接填写原始分数：当前 `config.json` 设置 `policy.correctness_max: 2.0`、`policy.relevance_max: 2.0`、`policy.repetition_min: 2.5`。当前评分范围为 0～4。提前停止设置统一放在 `policy.stopping`：`enabled: false`、`completeness_min: 4.0`、`correctness_min: 3.0`、`relevance_min: 3.0`。开启后须同时满足三个门槛。校验范围跟随各维度的评分等级数量。运行前激活所需 Python 环境，配置中不再指定解释器路径或选择后端。

综合质量分固定为 0～4 分。当前五档评分与默认权重下，计算为 `0.45*correctness + 0.30*relevance + 0.15*completeness + 0.10*(4-repetition)`。`utility_weights` 全部填写非负数（0～1，至少一项大于零），代码自动除以权重之和；评分档数变化时也会在内部换算。`policy.rollback.score_drop: 0.6` 表示调整后综合分下降超过 0.6 分就恢复原参数，不是下降 60%。这保留了原来的默认回退敏感度。回退不删除已生成文本，也不能证明因果关系。旧结果的效用数值采用旧尺度，不能与新结果直接比较。

## 5. 运行方式

在包含 `run.py` 的目录中由使用者自行执行：

| 命令 | 用途 | 加载 GPU 模型 | 调用 Jev |
|---|---|---|---|
| `python run.py check` | 检查配置和题目加载 | 否 | 否 |
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
题目数 × 种子数 × 模式数 × min(max_rounds, max_jev_calls)
```

10 道题、1 个种子、最多 8 轮时，run 最多 80 次请求，compare 最多 160 次请求，每次含四个评分问题。这是请求次数，不是费用报价。模型停止或提前耗尽其他预算可能减少实际请求数。

### 六个命令分别怎么用

先激活环境，再在仓库根目录运行。执行检查不会自动启动实验。

**check：检查配置与题目**

```shell
python run.py check
```

预期输出以 `Configuration valid; tasks=...; backend=python; mode=...` 开头。它读取主配置、参数定义、评分标准和题目，不加载模型，不验证密钥认证，也不消耗 Jev 额度。

**doctor：校验原生参数接口**

```shell
python run.py doctor
```

预期输出为 `Native SamplingParams validated. No model loaded and no Jev call made.`。它导入 vLLM 并用选定值构造 SamplingParams，不执行 GPU 推理，也不能证明后续所有参数组合都可用。

**smoke：短小的本地生成检查**

```shell
python run.py smoke
```

加载 Qwen，对第一题生成最多 8 个 token，在终端打印响应 JSON。不调用 Jev，也不创建正常实验结果目录。只得到短片段是正常情况，这不是答案质量测试。min_tokens 必须适合 8-token 预算。

**run：运行配置中的一种模式**

```shell
python run.py run
```

按照 `experiment.mode` 遍历全部题目和种子，调用 Jev，并为每个题目/种子保存结果目录。下面提供 fixed 和 adaptive 两种配置例子。

**compare：每题每种子运行两组**

```shell
python run.py compare
```

命令覆盖配置中的模式，每个题目/种子先 fixed 再 adaptive，两组都关闭评分触发的停止。它生成独立结果目录，不生成统计比较报告。两组都调用 Jev，因此相对一种模式，推理与评价开销可能接近两倍，实际取决于停止情况。

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

结果目录以 `_adaptive` 结尾，可能保持、调整、回退；若启用了评分停止，还可能据此结束。保持参数也是有效结果，不能据此认为没有使用 Jev。同样 10 道题、8 轮的请求上限为 80 次。

**C. 固定／自适应配对实验**

保留以上任一配置，命令自动选择两组：

```shell
python run.py compare
```

10 道题、1 个种子，最多生成 20 个实验目录，8 轮时最多 160 次请求。两组初值与预算一致，但关闭评分停止后，EOS 与预算停止仍有效，所以实际长度仍可能不同。分别查看 result.json 和 answer.txt；比较正确率仍需要独立标准答案判分器。

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

每个题目/种子/模式生成一个 `outputs/<timestamp>_<mode>/`，包含 `result.json` 和 `answer.txt`。重点查看每轮 `rounds[]` 的 `scores`、`decision`、`applied_parameters`、`generation_request`、耗时以及最终停止原因。

决策只是对下一段的提议，**下一轮实际请求才证明新参数被使用**。`decision_will_execute` 也不能单独证明下一次调用已成功。

`completed` 表示循环正常结束，不代表答案正确。结束可能源于模型、token/上下文/轮数/调用预算，或启用的评分停止。Ctrl+C 通常会保存 interrupted 状态；强制结束进程可能留下 running 状态。程序保留部分记录。重跑会从头开始，当前不支持断点续跑或自动付费重试；发生异常会中止后续实验循环。

配置好密钥后，可将控制台输出存到本地已有日志目录：

```powershell
New-Item -ItemType Directory -Force outputs | Out-Null
python run.py compare 2>&1 | Tee-Object -FilePath outputs/compare.log
```

此 PowerShell 示例将控制台日志保存在仓库的 outputs 目录。日志可能含题目和生成内容，完整实验依据应以保存结果为准。

## 7. 测试与故障排查

仅开发工作区可选：如果另行取得了符合开发目录布局的父级测试目录，可执行：

```powershell
python -m unittest discover -s ../tests -v
```

测试使用模拟模型和评价客户端，不消耗 API 额度。单独克隆仓库时，需要取得父目录的测试文件后才能使用这个命令。

| 现象 | 检查方向 |
|---|---|
| 仍提示输入密钥 | 旧进程或旧代码；停止后使用更新后的代码重启，当前只读 jev.api_key |
| HTTP 401/403 | 密钥是否有效、组织权限是否正常 |
| Billing / out of funds | TypeSafe 组织余额 |
| 超时或 TLS 错误 | 网络、代理、超时设置；当前不自动重试 |
| 无法 import vllm | 当前解释器环境与所安装 wheel |
| 找不到 cl.exe | 可选 JIT 编译使用的 MSVC 开发者环境 |
| 显存不足 | 其他 GPU 进程、上下文长度、引擎显存设置 |
| min_tokens 报错 | 是否超过当轮实际剩余预算；smoke 只分配 8 个 token |
| 预算用完仍无最终答案 | 检查 thinking 输出，按需要有意识地提高预算 |

## 8. 实验边界与延伸阅读

每段都是独立的 generate 调用，历史 token 作为下一段提示词。presence/frequency penalty 的计数针对本次调用新生成 token；repetition penalty 还考虑提示词。跨片段的停止字符串匹配不作保证。参数在调用之间改变，不是在正在执行的生成内部热修改。前缀缓存可能减少重复计算，但不会使分段生成等同于一次连续生成。

Jev 和 `answer.txt` 使用累积 token 的原始解码，可能保留特殊 token 和停止内容；显示参数作用于原生显示文本。每段使用 `seed + step`。fixed/adaptive 共享初始值和预算，不保证随机轨迹相同，也不保证准确率提高。

更多信息见[实现说明](docs/implementation.md)、[Transformers 迁移说明](docs/transformers_to_vllm.md)和 [GSM8K 来源](https://github.com/openai/grade-school-math)。报告 benchmark 正确率前，应增加独立的答案判分器。
