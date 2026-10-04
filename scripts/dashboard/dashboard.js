"use strict";

const tasks = window.JEV_OVERVIEW.tasks;
const availableModes = window.JEV_OVERVIEW.modes || ["baseline", "fixed", "adaptive"];
const $ = id => document.getElementById(id);
const COLORS = {baseline: "#8f8f8f", fixed: "#8f8f8f", adaptive: "#1f6fb5"};
const COPY = {
  zh: {
    siteTitle: "绩效与推理成本",
    overviewEyebrow: "实验概览", overviewTitle: "绩效与推理成本",
    intro: "独立答案评分与实际推理成本。每道题按同一任务和种子配对；未能判定的答案不计入准确率。",
    batchLabel: "实验批次", controlLabel: "对照组", controlBaseline: "Baseline · 仅 Qwen", controlFixed: "Fixed · Jev 评分",
    filterLabel: "答案筛选", all: "全部", improved: "Adaptive 改进", regressed: "Adaptive 退步", ungraded: "未评分",
    searchLabel: "搜索任务", tokenTitle: "生成 token",
    groupFindings: "关键发现", groupScalars: "01 · 标量曲线", groupPaired: "02 · 配对关系", groupDistributions: "03 · 双指标权衡", groupOutcomes: "04 · 答案与控制开销",
    tokenDesc: "按任务顺序；超过 100 道时按连续任务分箱取均值。灰色为对照组，蓝色为 Adaptive。",
    timeTitle: "请求耗时", timeDesc: "生成与 Jev 请求的计时之和；超过 100 道时分箱取均值。",
    tokenScatterTitle: "配对 token", timeScatterTitle: "配对请求耗时",
    scatterDesc: "横轴为对照组，纵轴为 Adaptive；点在对角线下方表示 Adaptive 更少。超过 1,000 道时抽样显示点位。",
    tradeoffTitle: "token 与请求耗时如何共同变化", tradeoffDesc: "按同一任务的两个差值归类；等于零的任务单列。",
    meanToken: "平均 token 差", meanTime: "平均请求耗时差", fewerTokens: "token 减少", moreTokens: "token 增加",
    shorterTime: "耗时缩短", longerTime: "耗时变长", bothLower: "两项均降低", tokenOnly: "省 token，但更慢",
    timeOnly: "更快，但多用 token", bothHigher: "两项均增加", neutralCases: "持平或缺失", moreTaskIds: "更多任务",
    outcomeTitle: "配对答案结果", outcomeDesc: "只比较同一任务与种子；未评分单列，不计入正确率。",
    costTitle: "Jev 调用与 token 变化", costDesc: "横轴为 Adaptive Jev 调用次数，纵轴为 Adaptive 减对照组的生成 token。",
    bothCorrect: "均正确", bothIncorrect: "均错误", improvedOutcome: "改进", regressedOutcome: "退步", ungradedOutcome: "未评分",
    controlAxis: "对照组", adaptiveAxis: "Adaptive", taskCount: "任务数", zeroLine: "零线",
    tasksTitle: "任务明细", tasksDesc: "点击一行查看 Score、参数和逐轮成本。表格每页 50 道题。",
    thTask: "任务 / 种子", thControlAnswer: "对照答案", thAdaptiveAnswer: "Adaptive 答案",
    thDeltaToken: "Δ token", thDeltaTime: "Δ 请求耗时", thCalls: "Adaptive Jev 调用", thChanges: "实际参数变更",
    prev: "上一页", next: "下一页", traceEyebrow: "任务轨迹", close: "关闭",
    scoreTitle: "Jev Score 与效用", scoreDesc: "选择一项 0–1 归一化 Score，与效用逐轮对比。", scoreMetric: "Score 指标",
    roundTimeTitle: "生成与 Jev 请求耗时", roundTimeDesc: "逐轮计时，单位秒。",
    paramTitle: "采样参数轨迹", paramLabel: "参数", paramDesc: "显示各模式实际用于每轮生成的值",
    eventsTitle: "逐轮事件", thRound: "轮次", thTokenRange: "Token 区间", thScoreUtility: "最严重症状 / 效用",
    thJevRequests: "Jev 请求", thJevTokens: "Jev token 输入 / 输出", thDecision: "决策", thAppliedNext: "下一轮生效",
    answerSummary: "查看三组最终答案末段与结果文件路径",
    footnote: "准确率仅统计可独立判分的配对任务。Jev Score 是过程反馈，不等同于答案正确率。计时受任务长度、设备状态和模型加载影响；小样本结果仅说明本批次。",
    pairedTasks: "配对任务", runs: "条运行记录", tasks: "道题", rounds: "轮", gradedBoth: "道均可评分",
    accuracy: "独立答案正确率", accuracySub: "Adaptive / 对照组", accuracyDiff: "正确率差",
    accuracyDiffSub: "配对差异，仅限可评分任务", meanTokens: "平均生成 token 差",
    meanTime: "平均请求耗时差", jevCost: "Adaptive Jev 成本", tokenSub: "Adaptive − 对照组",
    timeSub: "生成 + Jev 请求", inputTokens: "输入", outputTokens: "输出",
    deltaNote: control => `Δtoken = token(Adaptive) − token(${control})；Δ秒 = [Qwen + Jev](Adaptive) − [Qwen + Jev](${control})`,
    tokenTip: "Adaptive 生成 token 数减去当前对照组的生成 token 数；负值表示更少。",
    timeTip: "Adaptive（Qwen 生成 + Jev 请求）耗时减去当前对照组相同口径的耗时；负值表示更短。",
    grade: {correct: "正确", incorrect: "错误", ungraded: "未评分"},
    action: {adjust: "调整", keep: "保持", rollback: "回退", stop: "停止"},
    score: {correctness: "正确性", relevance: "相关性", repetition: "重复性", completeness: "完整性", utility: "效用", scatter: "散乱", rigidity: "僵住", distortion: "扭曲", over_checking: "过度复核", under_checking: "复核不足", on_track: "在正轨", trouble: "症状总量"},
    answer: "答案", requestTime: "请求耗时", calls: "Jev 调用", changes: "实际变更",
    stopReason: "停止原因", loading: "正在读取逐轮记录…", loadError: "无法读取该任务的数据文件。",
    proposedOnly: "已提议；未在下一轮生效", generation: "Qwen 生成", requests: "Jev 请求",
    finalAnswer: "最终答案末段", resultPath: "结果文件"
  },
  en: {
    siteTitle: "Performance explorer",
    overviewEyebrow: "EXPERIMENT OVERVIEW", overviewTitle: "Performance & inference cost",
    intro: "Independently graded answers and measured inference cost. Tasks are paired by task ID and seed; ungraded answers are excluded from accuracy.",
    batchLabel: "Experiment batch", controlLabel: "Control", controlBaseline: "Baseline · Qwen only", controlFixed: "Fixed · Jev scoring",
    filterLabel: "Answer filter", all: "All", improved: "Adaptive improved", regressed: "Adaptive regressed", ungraded: "Ungraded",
    searchLabel: "Search tasks", tokenTitle: "Generated tokens",
    groupFindings: "Key findings", groupScalars: "01 · Scalar traces", groupPaired: "02 · Paired comparisons", groupDistributions: "03 · Joint cost changes", groupOutcomes: "04 · Outcomes & control cost",
    tokenDesc: "Task order; above 100 tasks, consecutive tasks are binned and averaged. Gray is the control, blue is adaptive.",
    timeTitle: "Request time", timeDesc: "Generation plus Jev request time; above 100 tasks, consecutive tasks are binned and averaged.",
    tokenScatterTitle: "Paired tokens", timeScatterTitle: "Paired request time",
    scatterDesc: "Control on x, adaptive on y; below the diagonal means less for adaptive. Above 1,000 tasks, points are sampled.",
    tradeoffTitle: "How do tokens and request time change together?", tradeoffDesc: "Classify both deltas for each paired task; exact ties are listed separately.",
    meanToken: "Mean token difference", meanTime: "Mean request-time difference", fewerTokens: "Fewer tokens", moreTokens: "More tokens",
    shorterTime: "Shorter time", longerTime: "Longer time", bothLower: "Both lower", tokenOnly: "Fewer tokens, slower",
    timeOnly: "Faster, more tokens", bothHigher: "Both higher", neutralCases: "Ties or missing", moreTaskIds: "more tasks",
    outcomeTitle: "Paired answer outcomes", outcomeDesc: "Matched task and seed only; ungraded tasks are separate and excluded from accuracy.",
    costTitle: "Jev calls vs token change", costDesc: "Adaptive Jev calls on x; adaptive minus control generated tokens on y.",
    bothCorrect: "Both correct", bothIncorrect: "Both incorrect", improvedOutcome: "Improved", regressedOutcome: "Regressed", ungradedOutcome: "Ungraded",
    controlAxis: "Control", adaptiveAxis: "Adaptive", taskCount: "Task count", zeroLine: "Zero line",
    tasksTitle: "Task details", tasksDesc: "Select a row for Scores, parameters, and per-round cost. 50 tasks per page.",
    thTask: "Task / seed", thControlAnswer: "Control answer", thAdaptiveAnswer: "Adaptive answer",
    thDeltaToken: "Δ tokens", thDeltaTime: "Δ request time", thCalls: "Adaptive Jev calls", thChanges: "Applied parameter changes",
    prev: "Previous", next: "Next", traceEyebrow: "TASK TRACE", close: "Close",
    scoreTitle: "Jev Score & utility", scoreDesc: "Select one normalized 0–1 Score to compare with utility by round.", scoreMetric: "Score metric",
    roundTimeTitle: "Generation & Jev request time", roundTimeDesc: "Measured time per round, in seconds.",
    paramTitle: "Sampling parameter trajectories", paramLabel: "Parameter", paramDesc: "Values actually used to generate each round",
    eventsTitle: "Round events", thRound: "Round", thTokenRange: "Token range", thScoreUtility: "Worst symptom / utility",
    thJevRequests: "Jev requests", thJevTokens: "Jev tokens in / out", thDecision: "Decision", thAppliedNext: "Applied next round",
    answerSummary: "View final-answer excerpts and result file paths for all three runs",
    footnote: "Accuracy includes only paired tasks with independently gradable answers. Jev Score is process feedback, not answer accuracy. Timing depends on task length, device state, and model loading; this small sample describes only this batch.",
    pairedTasks: "paired tasks", runs: "runs", tasks: "tasks", rounds: "rounds", gradedBoth: "graded in both runs",
    accuracy: "Independent answer accuracy", accuracySub: "Adaptive / control", accuracyDiff: "Accuracy difference",
    accuracyDiffSub: "Paired, gradable tasks only", meanTokens: "Mean generated-token difference",
    meanTime: "Mean request-time difference", jevCost: "Adaptive Jev cost", tokenSub: "Adaptive − control",
    timeSub: "Generation + Jev requests", inputTokens: "input", outputTokens: "output",
    deltaNote: control => `Δtokens = tokens(Adaptive) − tokens(${control}); Δseconds = [Qwen + Jev](Adaptive) − [Qwen + Jev](${control})`,
    tokenTip: "Adaptive generated tokens minus generated tokens for the selected control; negative means fewer.",
    timeTip: "Adaptive (Qwen generation + Jev requests) minus the same measured time for the selected control; negative means shorter.",
    grade: {correct: "Correct", incorrect: "Incorrect", ungraded: "Ungraded"},
    action: {adjust: "Adjust", keep: "Keep", rollback: "Rollback", stop: "Stop"},
    score: {correctness: "Correctness", relevance: "Relevance", repetition: "Repetition", completeness: "Completeness", utility: "Utility", scatter: "Scatter", rigidity: "Rigidity", distortion: "Distortion", over_checking: "Over-checking", under_checking: "Under-checking", on_track: "On track", trouble: "Trouble"},
    answer: "Answer", requestTime: "Request time", calls: "Jev calls", changes: "Applied changes",
    stopReason: "Stop reason", loading: "Loading round records…", loadError: "Could not load this task's data file.",
    proposedOnly: "Proposed; not applied next round", generation: "Qwen generation", requests: "Jev requests",
    finalAnswer: "Final-answer excerpt", resultPath: "Result file"
  }
};

const state = {control: availableModes.includes("baseline") ? "baseline" : "fixed", filter: "all", search: "", page: 0, language: "zh", detail: null};
try { state.language = localStorage.getItem("jev-dashboard-language") === "en" ? "en" : "zh"; } catch (_) {}
const t = key => COPY[state.language][key];
const fmt = (value, digits = 1) => value == null || !Number.isFinite(Number(value))
  ? "—" : Number(value).toLocaleString("en-US", {maximumFractionDigits: digits});
const delta = (left, right, unit = "") => left == null || right == null
  ? "—" : `${left - right > 0 ? "+" : ""}${fmt(left - right)}${unit}`;
const mean = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

function selectedTasks() {
  return tasks.filter(task => {
    const control = task.modes[state.control].grade;
    const adaptive = task.modes.adaptive.grade;
    if (state.search && !task.task.toLowerCase().includes(state.search)) return false;
    if (state.filter === "improved" && !(control === "incorrect" && adaptive === "correct")) return false;
    if (state.filter === "regressed" && !(control === "correct" && adaptive === "incorrect")) return false;
    if (state.filter === "ungraded" && control !== "ungraded" && adaptive !== "ungraded") return false;
    return true;
  });
}

function card(label, value, sub) {
  const node = element("div", null, "kpi");
  node.append(element("div", label, "label"), element("div", value, "value"), element("div", sub, "sub"));
  return node;
}

function renderKpis(rows) {
  const control = state.control;
  const graded = rows.filter(row => ["correct", "incorrect"].includes(row.modes[control].grade)
    && ["correct", "incorrect"].includes(row.modes.adaptive.grade));
  const n = graded.length;
  const controlCorrect = graded.filter(row => row.modes[control].grade === "correct").length;
  const adaptiveCorrect = graded.filter(row => row.modes.adaptive.grade === "correct").length;
  const meanTokens = mean(rows.map(row => row.modes.adaptive.generatedTokens - row.modes[control].generatedTokens));
  const meanSeconds = mean(rows.map(row => requestSeconds(row.modes.adaptive) - requestSeconds(row.modes[control])));
  const calls = rows.reduce((sum, row) => sum + row.modes.adaptive.jevCalls, 0);
  const input = rows.reduce((sum, row) => sum + (row.modes.adaptive.jevInputTokens || 0), 0);
  const output = rows.reduce((sum, row) => sum + (row.modes.adaptive.jevOutputTokens || 0), 0);
  $("kpis").replaceChildren(
    card(t("accuracy"), n ? `${fmt(adaptiveCorrect / n * 100)}% / ${fmt(controlCorrect / n * 100)}%` : "—", `${t("accuracySub")} · ${n} ${t("gradedBoth")}`),
    card(t("accuracyDiff"), n ? delta(adaptiveCorrect / n * 100, controlCorrect / n * 100, " pp") : "—", t("accuracyDiffSub")),
    card(t("meanTokens"), delta(meanTokens, 0), `${t("tokenSub")} · ${rows.length} ${t("tasks")}`),
    card(t("meanTime"), delta(meanSeconds, 0, " s"), `${t("timeSub")} · ${rows.length} ${t("tasks")}`),
    card(t("jevCost"), `${fmt(calls, 0)} calls`, `${fmt(input, 0)} ${t("inputTokens")} / ${fmt(output, 0)} ${t("outputTokens")} tokens`)
  );
}

function requestSeconds(run) {
  return Number.isFinite(run.generationSeconds) && Number.isFinite(run.jevSeconds)
    ? run.generationSeconds + run.jevSeconds : null;
}
function svgElement(tag, attributes = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, String(value));
  return node;
}

function chart(id, inputSeries, {ymin = null, ymax = null, percent = false} = {}) {
  let series = inputSeries;
  if (["token-chart", "time-chart"].includes(id) && series.some(item => item.values.length > 100)) {
    series = series.map(item => {
      const values = [];
      const width = Math.ceil(item.values.length / 100);
      for (let index = 0; index < item.values.length; index += width) {
        const bin = item.values.slice(index, index + width).filter(value => value != null);
        values.push(bin.length ? mean(bin) : null);
      }
      return {...item, values, rows: null};
    });
  }
  const W = 650, H = 250, margin = {left: 50, right: 16, top: 18, bottom: 38};
  const all = series.flatMap(item => item.values.filter(value => value != null && Number.isFinite(value)));
  let high = ymax ?? Math.max(...all, 1);
  const low = ymin ?? Math.min(0, ...all);
  if (high === low) high = low + 1;
  const count = Math.max(2, ...series.map(item => item.values.length));
  const x = index => margin.left + (W - margin.left - margin.right) * index / (count - 1);
  const y = value => H - margin.bottom - (value - low) / (high - low) * (H - margin.top - margin.bottom);
  const root = svgElement("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": id});
  for (let index = 0; index <= 4; index++) {
    const lineY = margin.top + (H - margin.top - margin.bottom) * index / 4;
    root.append(svgElement("line", {x1: margin.left, x2: W - margin.right, y1: lineY, y2: lineY, class: "gridline"}));
    const tick = svgElement("text", {x: margin.left - 7, y: lineY + 4, "text-anchor": "end", class: "tick"});
    tick.textContent = fmt(high - (high - low) * index / 4, percent ? 2 : 0);
    root.append(tick);
  }
  root.append(svgElement("line", {x1: margin.left, x2: W - margin.right, y1: H - margin.bottom, y2: H - margin.bottom, class: "axis"}));
  const tickCount = Math.min(count, 6);
  for (let index = 0; index < tickCount; index++) {
    const position = Math.round(index * (count - 1) / Math.max(1, tickCount - 1));
    const tick = svgElement("text", {x: x(position), y: H - 13, "text-anchor": "middle", class: "tick"});
    tick.textContent = position + 1;
    root.append(tick);
  }
  for (const item of series) {
    const points = item.values.map((value, index) => value == null ? null : `${x(index)},${y(value)}`).filter(Boolean);
    if (points.length > 1) root.append(svgElement("polyline", {points: points.join(" "), fill: "none", stroke: item.color, "stroke-width": 2, "stroke-linejoin": "round", ...(item.dash ? {"stroke-dasharray": item.dash} : {})}));
    item.values.forEach((value, index) => {
      if (value == null) return;
      const dot = svgElement("circle", {cx: x(index), cy: y(value), r: 3, fill: item.color});
      const title = svgElement("title");
      title.textContent = `${item.name} · ${item.rows?.[index]?.task || index + 1}: ${fmt(value, 3)}`;
      dot.append(title);
      if (item.rows?.[index]) { dot.classList.add("plot-point"); dot.onclick = () => loadDetail(item.rows[index]); }
      root.append(dot);
    });
  }
  const legend = element("div", null, "legend-row");
  for (const item of series) {
    const label = element("span", item.name);
    label.style.borderLeft = `9px solid ${item.color}`;
    label.style.paddingLeft = "6px";
    legend.append(label);
  }
  $(id).replaceChildren(root, legend);
}

function drawScatter(id, rows, xValue, yValue, xLabel, yLabel, {diagonal = false, zeroY = false} = {}) {
  const W = 650, H = 250, m = {left: 53, right: 20, top: 17, bottom: 43};
  const sampled = rows.length > 1000 ? rows.filter((_, index) => index % Math.ceil(rows.length / 1000) === 0) : rows;
  const points = sampled.map(row => ({row, x: xValue(row), y: yValue(row)}))
    .filter(point => Number.isFinite(point.x) && Number.isFinite(point.y));
  const maxX = Math.max(1, ...points.map(point => point.x));
  const minY = Math.min(0, ...points.map(point => point.y));
  const maxY = Math.max(1, ...points.map(point => point.y));
  const minX = Math.min(0, ...points.map(point => point.x));
  const maxBound = diagonal ? Math.max(maxX, maxY) : maxX;
  const x0 = diagonal ? 0 : minX, x1 = maxBound;
  const y0 = diagonal ? 0 : minY, y1 = diagonal ? maxBound : maxY;
  const X = value => m.left + (value - x0) / Math.max(1, x1 - x0) * (W - m.left - m.right);
  const Y = value => H - m.bottom - (value - y0) / Math.max(1, y1 - y0) * (H - m.top - m.bottom);
  const root = svgElement("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": id});
  for (let index = 0; index <= 4; index++) {
    const value = y0 + (y1 - y0) * index / 4;
    const lineY = Y(value);
    root.append(svgElement("line", {x1: m.left, x2: W - m.right, y1: lineY, y2: lineY, class: "gridline"}));
    const tick = svgElement("text", {x: m.left - 7, y: lineY + 4, "text-anchor": "end", class: "tick"});
    tick.textContent = fmt(value, 0);
    root.append(tick);
  }
  for (let index = 0; index <= 4; index++) {
    const value = x0 + (x1 - x0) * index / 4;
    const tick = svgElement("text", {x: X(value), y: H - 20, "text-anchor": "middle", class: "tick"});
    tick.textContent = fmt(value, 0);
    root.append(tick);
  }
  if (diagonal) root.append(svgElement("line", {x1: X(0), y1: Y(0), x2: X(maxBound), y2: Y(maxBound), stroke: COLORS.baseline, "stroke-width": 1.5, "stroke-dasharray": "5 4"}));
  if (zeroY && y0 < 0 && y1 > 0) root.append(svgElement("line", {x1: m.left, y1: Y(0), x2: W - m.right, y2: Y(0), stroke: COLORS.baseline, "stroke-width": 1.5, "stroke-dasharray": "5 4"}));
  for (const point of points) {
    const dot = svgElement("circle", {cx: X(point.x), cy: Y(point.y), r: 4.5, fill: COLORS.adaptive, opacity: .78, class: "plot-point"});
    const title = svgElement("title");
    title.textContent = `${point.row.task} · ${xLabel}: ${fmt(point.x)} · ${yLabel}: ${fmt(point.y)}`;
    dot.append(title);
    dot.onclick = () => loadDetail(point.row);
    root.append(dot);
  }
  const xTitle = svgElement("text", {x: (m.left + W - m.right) / 2, y: H - 1, "text-anchor": "middle", class: "label"});
  xTitle.textContent = xLabel;
  root.append(xTitle);
  const yTitle = svgElement("text", {x: 12, y: H / 2, transform: `rotate(-90 12 ${H / 2})`, "text-anchor": "middle", class: "label"});
  yTitle.textContent = yLabel;
  root.append(yTitle);
  $(id).replaceChildren(root);
}

function renderTradeoff(rows) {
  const allChanges = rows.map(row => {
    const adaptive = row.modes.adaptive, control = row.modes[state.control];
    const adaptiveSeconds = requestSeconds(adaptive), controlSeconds = requestSeconds(control);
    return {row,
      tokens: Number.isFinite(adaptive.generatedTokens) && Number.isFinite(control.generatedTokens)
        ? adaptive.generatedTokens - control.generatedTokens : NaN,
      seconds: Number.isFinite(adaptiveSeconds) && Number.isFinite(controlSeconds)
        ? adaptiveSeconds - controlSeconds : NaN
    };
  });
  const changes = allChanges.filter(change => Number.isFinite(change.tokens) && Number.isFinite(change.seconds));
  const n = changes.length;
  $("tradeoff-count").textContent = `n = ${fmt(n, 0)}`;
  const tokenMean = mean(changes.map(change => change.tokens));
  const timeMean = mean(changes.map(change => change.seconds));
  const stats = $("tradeoff-metrics");
  stats.replaceChildren();
  for (const [label, value, unit, reduced, direction] of [
    [t("meanToken"), tokenMean, " token", changes.filter(change => change.tokens < 0).length, t("fewerTokens")],
    [t("meanTime"), timeMean, " s", changes.filter(change => change.seconds < 0).length, t("shorterTime")]
  ]) {
    const card = element("div", null, "tradeoff-stat");
    card.append(element("div", label, "tradeoff-stat-label"),
      element("strong", value == null ? "—" : `${value > 0 ? "+" : ""}${fmt(value)}${unit}`, `tradeoff-stat-value ${value < 0 ? "negative" : value > 0 ? "positive" : ""}`),
      element("div", `${direction}: ${reduced} / ${n}`, "tradeoff-stat-sub"));
    stats.append(card);
  }
  const groups = {bothLower: [], tokenOnly: [], timeOnly: [], bothHigher: [],
    neutralCases: allChanges.filter(change => !Number.isFinite(change.tokens) || !Number.isFinite(change.seconds)).map(change => change.row)};
  for (const change of changes) {
    if (change.tokens < 0 && change.seconds < 0) groups.bothLower.push(change.row);
    else if (change.tokens < 0 && change.seconds > 0) groups.tokenOnly.push(change.row);
    else if (change.tokens > 0 && change.seconds < 0) groups.timeOnly.push(change.row);
    else if (change.tokens > 0 && change.seconds > 0) groups.bothHigher.push(change.row);
    else groups.neutralCases.push(change.row);
  }
  const matrix = $("tradeoff-matrix");
  matrix.replaceChildren();
  matrix.append(element("div", "", "tradeoff-corner"),
    element("div", `${t("shorterTime")}  Δs < 0`, "tradeoff-axis"),
    element("div", `${t("longerTime")}  Δs > 0`, "tradeoff-axis"));
  for (const [axis, left, right] of [
    [t("fewerTokens"), "bothLower", "tokenOnly"],
    [t("moreTokens"), "timeOnly", "bothHigher"]
  ]) {
    matrix.append(element("div", `${axis}  ΔT ${axis === t("fewerTokens") ? "<" : ">"} 0`, "tradeoff-axis tradeoff-row-axis"));
    for (const key of [left, right]) {
      const cell = element("div", null, `tradeoff-cell ${key}`);
      cell.append(element("strong", fmt(groups[key].length, 0), "tradeoff-cell-count"), element("span", t(key), "tradeoff-cell-label"));
      const examples = element("div", null, "tradeoff-examples");
      for (const row of groups[key].slice(0, 4)) {
        const button = element("button", row.task, "tradeoff-task");
        button.type = "button";
        button.onclick = () => loadDetail(row);
        examples.append(button);
      }
      if (groups[key].length > 4) examples.append(element("span", `+${groups[key].length - 4} ${t("moreTaskIds")}`, "tradeoff-more"));
      cell.append(examples);
      matrix.append(cell);
    }
  }
  $("tradeoff-neutral").textContent = groups.neutralCases.length
    ? `${t("neutralCases")}: ${groups.neutralCases.length}` : "";
}

function drawOutcomes(rows) {
  const counts = {bothCorrect: 0, improvedOutcome: 0, regressedOutcome: 0, bothIncorrect: 0, ungradedOutcome: 0};
  for (const row of rows) {
    const control = row.modes[state.control].grade, adaptive = row.modes.adaptive.grade;
    if (![control, adaptive].every(grade => ["correct", "incorrect"].includes(grade))) counts.ungradedOutcome++;
    else if (control === "correct" && adaptive === "correct") counts.bothCorrect++;
    else if (control === "incorrect" && adaptive === "correct") counts.improvedOutcome++;
    else if (control === "correct" && adaptive === "incorrect") counts.regressedOutcome++;
    else counts.bothIncorrect++;
  }
  const W = 650, H = 250, m = {left: 135, right: 32, top: 15, bottom: 23};
  const max = Math.max(1, ...Object.values(counts));
  const root = svgElement("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "outcome-chart"});
  Object.entries(counts).forEach(([key, count], index) => {
    const y = m.top + index * 43;
    const label = svgElement("text", {x: m.left - 10, y: y + 21, "text-anchor": "end", class: "label"});
    label.textContent = t(key);
    root.append(label);
    const bar = svgElement("rect", {x: m.left, y: y + 5, width: count / max * (W - m.left - m.right), height: 23,
      fill: key === "improvedOutcome" ? "#1f6fb5" : key === "regressedOutcome" ? "#c0392b" : key === "bothCorrect" ? "#8f8f8f" : "#d4d4d4"});
    const title = svgElement("title"); title.textContent = `${t(key)}: ${count}`; bar.append(title);
    root.append(bar);
    const value = svgElement("text", {x: m.left + count / max * (W - m.left - m.right) + 6, y: y + 21, class: "label"});
    value.textContent = count; root.append(value);
  });
  $("outcome-chart").replaceChildren(root);
}

function renderOverview() {
  const rows = selectedTasks();
  $("dataset-count").textContent = `${window.JEV_OVERVIEW.batch || ""} · ${tasks.length} ${t("pairedTasks")} · ${tasks.length * availableModes.length} ${t("runs")}`;
  $("delta-note").textContent = t("deltaNote")(state.control === "baseline" ? "Baseline" : "Fixed");
  $("th-delta-token").title = t("tokenTip");
  $("th-delta-time").title = t("timeTip");
  renderKpis(rows);
  chart("token-chart", [
    {name: state.control, color: COLORS[state.control], values: rows.map(row => row.modes[state.control].generatedTokens), rows},
    {name: "adaptive", color: COLORS.adaptive, values: rows.map(row => row.modes.adaptive.generatedTokens), rows}
  ]);
  chart("time-chart", [
    {name: state.control, color: COLORS[state.control], values: rows.map(row => requestSeconds(row.modes[state.control])), rows},
    {name: "adaptive", color: COLORS.adaptive, values: rows.map(row => requestSeconds(row.modes.adaptive)), rows}
  ]);
  drawScatter("token-scatter", rows,
    row => row.modes[state.control].generatedTokens, row => row.modes.adaptive.generatedTokens,
    t("controlAxis"), t("adaptiveAxis"), {diagonal: true});
  drawScatter("time-scatter", rows,
    row => requestSeconds(row.modes[state.control]), row => requestSeconds(row.modes.adaptive),
    t("controlAxis"), t("adaptiveAxis"), {diagonal: true});
  renderTradeoff(rows);
  drawOutcomes(rows);
  drawScatter("cost-scatter", rows,
    row => row.modes.adaptive.jevCalls,
    row => row.modes.adaptive.generatedTokens - row.modes[state.control].generatedTokens,
    t("thCalls"), t("thDeltaToken"), {zeroY: true});
  if (typeof window.renderFindings === "function") window.renderFindings(rows);
  const pages = Math.max(1, Math.ceil(rows.length / 50));
  state.page = Math.min(state.page, pages - 1);
  $("table-count").textContent = `${rows.length} ${t("tasks")}`;
  $("page-status").textContent = `${state.page + 1} / ${pages}`;
  $("prev").disabled = state.page === 0;
  $("next").disabled = state.page >= pages - 1;
  const body = $("task-rows");
  body.replaceChildren();
  for (const row of rows.slice(state.page * 50, (state.page + 1) * 50)) {
    const control = row.modes[state.control], adaptive = row.modes.adaptive;
    const tr = element("tr");
    const values = [
      `${row.task} · ${row.seed}`, t("grade")[control.grade] || control.grade,
      t("grade")[adaptive.grade] || adaptive.grade,
      delta(adaptive.generatedTokens, control.generatedTokens),
      delta(requestSeconds(adaptive), requestSeconds(control), " s"),
      fmt(adaptive.jevCalls, 0), fmt(adaptive.executedChanges, 0)
    ];
    values.forEach((value, index) => {
      const gradeClass = index === 2 && adaptive.grade === "correct" && control.grade === "incorrect" ? "good"
        : index === 2 && adaptive.grade === "incorrect" && control.grade === "correct" ? "bad" : "";
      tr.append(element("td", value, gradeClass));
    });
    tr.onclick = () => loadDetail(row);
    body.append(tr);
  }
}

function loadDetail(row) {
  state.detail = null;
  $("detail").hidden = false;
  $("detail-title").textContent = `${row.task} · seed ${row.seed}`;
  $("prompt").textContent = t("loading");
  $("detail").scrollIntoView({behavior: "smooth", block: "start"});
  if (window.JEV_TASKS[row.key]) { renderDetail(window.JEV_TASKS[row.key]); return; }
  const script = document.createElement("script");
  script.src = `data/tasks/${row.key}.js`;
  script.onload = () => renderDetail(window.JEV_TASKS[row.key]);
  script.onerror = () => { $("prompt").textContent = t("loadError"); };
  document.body.append(script);
}

function renderDetail(detail) {
  if (!detail) return;
  state.detail = detail;
  $("prompt").textContent = detail.prompt;
  const stats = $("run-stats");
  stats.replaceChildren();
  for (const mode of availableModes) {
    const run = detail.modes[mode], node = element("div", null, "run-card");
    node.append(
      element("strong", mode.toUpperCase()),
      element("div", `${t("answer")}: ${t("grade")[run.grade] || run.grade} · ${fmt(run.generatedTokens, 0)} Qwen tokens`),
      element("div", `${fmt(requestSeconds(run))} s ${t("requestTime")} · ${run.jevCalls} ${t("calls")}`),
      element("div", `${run.rounds.length} ${t("rounds")} · ${run.executedChanges} ${t("changes")} · ${t("stopReason")}: ${run.stopReason || "—"}`)
    );
    stats.append(node);
  }
  const rounds = detail.modes.adaptive.rounds;
  const scoreSelect = $("score-metric"), priorScore = scoreSelect.value;
  const present = Object.keys(rounds.find(round => Object.keys(round.scores || {}).length)?.scores || {});
  scoreSelect.replaceChildren(...present.map(key => {
    const option = element("option", t("score")[key]); option.value = key; return option;
  }));
  scoreSelect.value = priorScore || "correctness";
  scoreSelect.onchange = () => renderScore(detail);
  renderScore(detail);
  chart("round-time-chart", [
    {name: t("generation"), color: COLORS.adaptive, values: rounds.map(round => round.generationSeconds)},
    {name: t("requests"), color: COLORS.fixed, values: rounds.map(round => round.jevSeconds)}
  ]);
  const names = [...new Set(rounds.flatMap(round => Object.keys(round.parameters)))].filter(name => ["number", "boolean"].includes(typeof rounds[0]?.parameters[name]));
  const select = $("parameter"), prior = select.value;
  select.replaceChildren(...names.map(name => { const option = element("option", name); option.value = name; return option; }));
  select.value = names.includes(prior) ? prior : names.includes("temperature") ? "temperature" : names[0];
  select.onchange = () => renderParameter(detail);
  renderParameter(detail);
  const body = $("round-rows");
  body.replaceChildren();
  rounds.forEach((round, index) => {
    const tr = element("tr");
    const applied = round.executedNextRound ? round.changedNextRound.join(", ") : round.proposal ? t("proposedOnly") : "—";
    [index + 1, `${round.tokenStart}–${round.tokenEnd}`, roundSummary(round),
      round.jevCalls, `${round.jevInputTokens} / ${round.jevOutputTokens}`, t("action")[round.action] || round.action || "—", applied]
      .forEach(value => tr.append(element("td", value)));
    body.append(tr);
  });
  const answers = $("answers");
  answers.replaceChildren();
  for (const mode of availableModes) {
    const run = detail.modes[mode];
    answers.append(element("h4", `${mode} · ${t("finalAnswer")}`), element("pre", run.finalAnswer || "(empty)"), element("small", `${t("resultPath")}: ${run.resultPath}`));
  }
}

function renderParameter(detail) {
  const name = $("parameter").value;
  if (!name) return;
  chart("param-chart", availableModes.map(mode => ({
    name: mode, color: COLORS[mode], dash: mode === "fixed" ? "5 4" : null,
    values: detail.modes[mode].rounds.map(round => {
      const value = round.parameters[name];
      return typeof value === "boolean" ? Number(value) : typeof value === "number" ? value : null;
    })
  })));
}

/* Runs made before the symptom scores have `utility`; later runs have `trouble` (higher is worse). */
const roundLevel = round => round.trouble ?? round.utility;
const levelName = rounds => t("score")[rounds.some(round => round.trouble != null) ? "trouble" : "utility"];
const roundSummary = round => round.trouble != null
  ? `${t("score")[round.worst] || round.worst} ${fmt(round.trouble, 2)}`
  : `${fmt(round.scores.correctness, 2)} / ${fmt(round.utility, 2)}`;

function renderScore(detail) {
  const key = $("score-metric").value;
  const rounds = detail.modes.adaptive.rounds;
  chart("score-chart", [
    {name: t("score")[key], color: COLORS.adaptive, values: rounds.map(round => round.scores[key])},
    {name: levelName(rounds), color: COLORS.baseline, values: rounds.map(roundLevel)}
  ], {ymin: 0, ymax: 1, percent: true});
}

function setLanguage(language) {
  state.language = language;
  if (window.updateBatchLabels) window.updateBatchLabels(language);
  document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  document.title = `Jev · ${t("siteTitle")}`;
  document.querySelectorAll("[data-i18n]").forEach(node => { node.textContent = t(node.dataset.i18n); });
  $("lang-zh").setAttribute("aria-pressed", String(language === "zh"));
  $("lang-en").setAttribute("aria-pressed", String(language === "en"));
  try { localStorage.setItem("jev-dashboard-language", language); } catch (_) {}
  renderOverview();
  if (state.detail) renderDetail(state.detail);
}

$("control").onchange = event => { state.control = event.target.value; state.page = 0; renderOverview(); };
$('control').querySelectorAll('option').forEach(option => { option.hidden = !availableModes.includes(option.value); });
$('control').value = state.control;
$("grade-filter").onchange = event => { state.filter = event.target.value; state.page = 0; renderOverview(); };
$("search").oninput = event => { state.search = event.target.value.trim().toLowerCase(); state.page = 0; renderOverview(); };
$("prev").onclick = () => { state.page--; renderOverview(); };
$("next").onclick = () => { state.page++; renderOverview(); };
$("close-detail").onclick = () => { $("detail").hidden = true; state.detail = null; };
$("lang-zh").onclick = () => setLanguage("zh");
$("lang-en").onclick = () => setLanguage("en");
setLanguage(state.language);
