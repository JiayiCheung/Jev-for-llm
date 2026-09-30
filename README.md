# Jev × vLLM 推理参数控制

统一配置：config.json。统一入口：run.py。无需安装客户端依赖。

## 目录

- config.json：路径、模型服务、Jev评分标准、采样、控制阈值、预算。
- data/tasks.jsonl：题库，reference仅保存，不发送给Qwen或Jev。
- src/jev_vllm/config.py：配置加载、相对路径解析和校验。
- clients.py：HTTP与认证；adapters.py：Jev输入输出转换。
- policy.py：调整、观察、保留、撤回、冷却与停止。
- runner.py：token续写、执行、逐轮日志；cli.py：命令入口。
- tests/：离线测试；docs/：实施和验证记录；outputs/：运行结果。

## 运行

先检查config.json中的paths.python和paths.model。相对路径以配置所在目录为基准。

第一个终端：

    conda activate vllm
    cd G:\Article\Jev\Code
    python run.py check
    python run.py serve

等待Application startup complete并保持服务终端开启。另一个终端：

    conda activate vllm
    cd G:\Article\Jev\Code
    python run.py doctor
    python run.py run

可用 --config 指定其他配置。doctor只检查模型服务连接，不调用Jev。10061表示服务未连通。

Key从配置指定的TYPESAFE_API_KEY环境变量或隐藏输入读取，不落盘。run把题目及生成文本发送给TypeSafe，默认每题每种子最多8次评分请求，每次4个Score。不自动重试收费请求。

## 对照与测试

    python run.py compare
    python run.py summarize
    python -m unittest discover -s tests -v

compare运行fixed和adaptive：相同题目、种子、初始参数、分段与预算；两组均调用Jev，fixed不改变采样。对照强制关闭评分提前停止。默认最多16次调用。summarize只汇总运行指标，不自动计算准确率。

## 配置

| 节 | 内容 |
|---|---|
| paths | Python、模型、题库、输出路径 |
| server | 地址端口、模型别名、精度、显存、上下文、并发、超时 |
| jev | API地址端点、模型、密钥环境变量名称、超时、指令与criteria |
| generation | segmented后端、思考开关、分段/总token和轮数 |
| sampling | temperature、top_p、top_k、repetition_penalty初值 |
| experiment | 模式、种子列表、每个实验的Jev调用预算 |
| policy | 置信度、冷却、停止开关、触发阈值、步长、上下界、反馈权重、撤回阈值 |

四个维度名称是策略接口契约；正确性、相关性、完整度越高越好，重复越高越差。criteria可改但语义方向须保持。等级归一化不是正确概率。当前调整三个参数，top_k保持配置值。

## 反馈设计

低置信度保持；明显错误或偏题时收窄采样，严重重复时提高重复惩罚。记录调整前参数及加权评分，下次可靠评分明显下降则撤回，否则保留，并遵守冷却。评分完整度提前停止默认关闭。

这是可替换的启发式基线，不是学习型决策器。前后变化不是因果证明，参数撤回不回滚错误文本。效果需要多题多种子、独立答案评测与固定参数对照。

## 执行边界

当前采用原始token ID跨请求分段续写，模板只应用一次。不是同一次请求内逐token热修改，可能重新prefill；引擎内部暂停/更新需要后续独立开发。

result.json保存配置快照、环境版本、题目种子、实际请求响应、评分、决策、参数和token区间。answer.txt是累计原始文本。Key和认证头不记录，结果包含题目文本。

decision是提议；下一轮applied_parameters及generation_request记录实际提交。decision_will_execute仅表示计划继续，失败时以实际请求为准。completed不等于答案正确/完整。异常保存已有结果，无自动续跑。耗时是请求耗时而非纯GPU耗时。

## 来源和状态

TypeSafe格式：https://docs.typesafe.ai/introduction/quickstart
Windows版本：https://github.com/SystemPanic/vllm-windows
本地vLLM0.29.0的tokenize/protocol.py与completion/protocol.py已核实token接口。

现有服务环境Python3.12、torch2.11+cu130、vLLM0.29.0社区版。13项离线测试及配置检查通过，尚未完成真实GPU与付费Jev联调。这是研究原型，不是某篇论文的正式复现。
