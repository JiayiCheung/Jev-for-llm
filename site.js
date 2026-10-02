const copy = {
  zh: {
    skip: "跳到摘要", navAbstract: "摘要", navMethod: "方法", navEvaluation: "实验",
    status: "研究原型 · 项目主页", title: "让语言模型在生成过程中调整采样参数",
    subtitle: "Jev 引导的推理时参数控制",
    heroSummary: "语言模型分段生成，Jev 对新片段评分，并为下一段选择参数调整方向与具体值。",
    modelLabel: "生成模型", modelText: "按当前参数生成一个片段",
    judgeLabel: "外部判断", judgeText: "四项评分 · 参数动作 Choice",
    nextLabel: "下一段", nextTitle: "更新采样参数", nextText: "仅对选中的参数应用合法值",
    engineLabel: "推理框架", engineText: "按新参数运行 Qwen", feedbackMobile: "↰ 返回 Qwen，生成下一段",
    teaserCaption: "方法概览。Jev 不生成答案；它评价本段文本，并在允许的参数范围内辅助下一段生成。固定参数组只记录评分。",
    abstractTitle: "摘要",
    abstractBody: "大语言模型通常在整道题中使用同一套采样设置。本项目研究能否利用生成过程中的外部反馈，在片段之间调整这些设置。Qwen 通过 vLLM 生成文本；Jev 分别评价正确性、相关性、重复性和完整性，再从参数类型对应的合法动作中选择调整方向，必要时选择具体数值。程序保留每轮评分、决策、实际生效参数和答案快照，以便后续分析质量与推理成本。",
    methodTitle: "方法", methodOneTitle: "分段生成与评分",
    methodOneBody: "每段生成后，Jev 按四项规则返回 0–4 的 Score；程序映射到 0–1 后用于控制决策。评分针对已经生成的文本。",
    methodTwoTitle: "按参数类型选择动作",
    methodTwoBody: "程序读取 parameters.json 中的定义，为数值、布尔、枚举和可空参数构建不同的 Choice。Jev 先选方向，再在需要时选具体值。",
    methodThreeTitle: "下一段生效并记录",
    methodThreeBody: "参数变化只作用于下一段。result.json 记录请求、反馈和实际使用的参数；answer.txt 保留每轮结束时的累计答案。",
    workflowTitle: "完整流程",
    workflowAlt: "单次 run 的完整流程图：初始化参数、vLLM 分段生成、Jev 评分和选择、回退冷却、记录与下一轮参数反馈",
    evaluationTitle: "实验结果",
    resourcesTitle: "代码与复现", resourcesBody: "环境搭建、配置文件格式、全部运行模式与输出字段见 README；参数类型和调用链在实现文档中说明。",
    parametersDoc: "参数示例 ↗", implementationDoc: "实现说明 ↗", footer: "研究原型 · 代码见仓库"
  },
  en: {
    skip: "Skip to abstract", navAbstract: "Abstract", navMethod: "Method", navEvaluation: "Experiments",
    status: "Research prototype · project page", title: "Adapting Sampling Parameters During Language Model Generation",
    subtitle: "Jev-guided inference-time parameter control",
    heroSummary: "A language model generates in segments. Jev scores each new segment and helps select parameter changes for the next one.",
    modelLabel: "Generator", modelText: "Generate one segment with current settings",
    judgeLabel: "External judgment", judgeText: "Four Scores · parameter-action Choices",
    nextLabel: "Next segment", nextTitle: "Update sampling", nextText: "Apply legal values to selected parameters",
    engineLabel: "Inference framework", engineText: "Run Qwen with updated settings", feedbackMobile: "↰ Return to Qwen for the next segment",
    teaserCaption: "Method overview. Jev does not write the answer: it evaluates the latest text and guides the next segment within declared parameter bounds. The fixed control records Scores without changing settings.",
    abstractTitle: "Abstract",
    abstractBody: "Language models commonly use one sampling configuration for an entire problem. This project asks whether external feedback during generation can guide changes between segments. Qwen generates text through vLLM; Jev evaluates correctness, relevance, repetition, and completeness. Type-specific Choices then select feasible parameter actions and, when needed, exact values. The program retains per-round Scores, decisions, applied parameters, and answer snapshots for later analysis of quality and inference cost.",
    methodTitle: "Method", methodOneTitle: "Generate and score segments",
    methodOneBody: "After each segment, Jev returns four 0–4 Scores. The controller maps them to 0–1 for decisions. Scores describe text already generated.",
    methodTwoTitle: "Choose type-specific actions",
    methodTwoBody: "Definitions in parameters.json yield different Choices for numeric, boolean, enum, and nullable fields. Jev selects a direction first, then an exact value when needed.",
    methodThreeTitle: "Apply and record the next step",
    methodThreeBody: "Changes take effect on the next segment only. result.json keeps requests, feedback, and applied settings; answer.txt retains the cumulative answer after each round.",
    workflowTitle: "Full workflow",
    workflowAlt: "Full single-run workflow: parameter initialization, segmented vLLM generation, Jev scoring and choices, rollback, records, and next-round feedback",
    evaluationTitle: "Experimental results",
    resourcesTitle: "Code and reproduction", resourcesBody: "See the README for setup, configuration, run modes, and outputs. The supporting docs describe parameter types and the call chain.",
    parametersDoc: "Parameter examples ↗", implementationDoc: "Implementation notes ↗", footer: "Research prototype · code in the repository"
  }
};

function render(language) {
  const strings = copy[language];
  document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach(element => {
    element.textContent = strings[element.dataset.i18n];
  });
  const paths = language === "zh"
    ? {readme: "docs/README.zh-CN.md", parameters: "docs/parameter_examples.zh-CN.md", implementation: "docs/implementation.zh-CN.md"}
    : {readme: "README.md", parameters: "docs/parameter_examples.md", implementation: "docs/implementation.md"};
  document.querySelectorAll("[data-doc]").forEach(link => {
    link.href = `https://github.com/JiayiCheung/Jev-for-llm/blob/main/${paths[link.dataset.doc]}`;
  });
  const workflowImage = document.querySelector("[data-workflow-image]");
  const workflowPath = `workflow_${language}.svg?v=3`;
  workflowImage.src = workflowPath;
  workflowImage.alt = strings.workflowAlt;
  document.querySelector("[data-workflow-link]").href = workflowPath;
  document.querySelectorAll("[data-lang]").forEach(button => {
    button.setAttribute("aria-pressed", String(button.dataset.lang === language));
  });
}

document.querySelectorAll("[data-lang]").forEach(button => {
  button.addEventListener("click", () => render(button.dataset.lang));
});
render("zh");
