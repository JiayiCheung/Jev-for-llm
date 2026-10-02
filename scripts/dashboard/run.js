"use strict";

const report = window.JEV_OVERVIEW;
const $ = id => document.getElementById(id);
const state = {language: "zh", filter: "all", search: "", page: 0, detail: null};
try { state.language = localStorage.getItem("jev-dashboard-language") === "en" ? "en" : "zh"; } catch (_) {}
const words = {
  zh: {nav: "实验批次", allBatches: "全部批次", eyebrow: "单模式实验", intro: "独立答案评分与实际推理成本；每条记录是一道任务与一个种子的运行。", completed: "条已完成", total: "条记录", filter: "答案筛选", filters: ["全部", "正确", "错误", "未评分"], search: "搜索任务", accuracy: "答案正确率", graded: "条可评分", meanTokens: "平均生成 token", meanTime: "平均请求耗时", meanCalls: "平均 Jev 调用", totalCalls: "Jev 调用总数", charts: "01 · 任务趋势", tokenTitle: "生成 token", chartNote: "按任务顺序；超过 100 条时按连续记录分箱取均值。", timeTitle: "请求耗时", timeNote: "Qwen 生成与 Jev 请求的计时之和，单位秒。", table: "02 · 逐题记录", taskTitle: "任务明细", taskNote: "每页 50 条；点击任务查看逐轮记录。", task: "任务 / 种子", answer: "答案", time: "请求耗时", calls: "Jev 调用", changes: "参数变更", prev: "上一页", next: "下一页", detail: "任务轨迹", close: "关闭", rounds: "逐轮记录", round: "轮次", score: "Score / 效用", roundTime: "生成 / Jev 秒", action: "决策", params: "实际采样参数", answerLabel: "查看答案末段和结果路径", footnote: "正确率只统计可独立判分的已完成任务；未评分任务不计入分母。本页只描述所选批次，不代表与其他实验可直接比较。", grade: {correct: "正确", incorrect: "错误", ungraded: "未评分"}, loading: "正在加载逐轮记录…", failed: "任务记录加载失败"},
  en: {nav: "Experiment", allBatches: "All batches", eyebrow: "SINGLE-MODE EXPERIMENT", intro: "Independent answer grades and measured inference cost. Each record is one task and seed.", completed: "completed", total: "records", filter: "Answer filter", filters: ["All", "Correct", "Incorrect", "Ungraded"], search: "Search tasks", accuracy: "Answer accuracy", graded: "gradable", meanTokens: "Mean generated tokens", meanTime: "Mean request time", meanCalls: "Mean Jev calls", totalCalls: "Total Jev calls", charts: "01 · TASK TRENDS", tokenTitle: "Generated tokens", chartNote: "Task order; above 100 records, consecutive records are binned and averaged.", timeTitle: "Request time", timeNote: "Qwen generation plus Jev request time, in seconds.", table: "02 · RUN RECORDS", taskTitle: "Task details", taskNote: "50 rows per page; select a task for round records.", task: "Task / seed", answer: "Answer", time: "Request time", calls: "Jev calls", changes: "Parameter changes", prev: "Previous", next: "Next", detail: "TASK TRACE", close: "Close", rounds: "Round records", round: "Round", score: "Score / utility", roundTime: "Generation / Jev seconds", action: "Action", params: "Applied sampling parameters", answerLabel: "Show final-answer excerpt and result path", footnote: "Accuracy includes only independently gradable completed runs. Ungraded runs are excluded. This page describes one batch and does not establish comparability with other experiments.", grade: {correct: "Correct", incorrect: "Incorrect", ungraded: "Ungraded"}, loading: "Loading round records…", failed: "Could not load the task record"}
};
const t = key => words[state.language][key];
const fmt = (value, digits = 1) => value == null || !Number.isFinite(Number(value)) ? "—" : Number(value).toLocaleString("en-US", {maximumFractionDigits: digits});
const text = (id, value) => { $(id).textContent = value; };
const cell = value => { const td = document.createElement("td"); td.textContent = value; return td; };
const average = values => { const valid = values.filter(value => Number.isFinite(value)); return valid.length ? valid.reduce((a, b) => a + b, 0) / valid.length : null; };

function visible() {
  return report.runs.filter(run => (!state.search || run.task.toLowerCase().includes(state.search)) &&
    (state.filter === "all" || run.grade === state.filter));
}

function drawChart(id, rows, key, unit) {
  const target = $(id);
  target.replaceChildren();
  if (!rows.length) return;
  const step = Math.ceil(rows.length / 100);
  const values = [];
  for (let i = 0; i < rows.length; i += step) values.push(average(rows.slice(i, i + step).map(row => row[key])));
  const data = values.map(value => value || 0), max = Math.max(1, ...data);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 800 220");
  const line = (tag, attributes) => { const node = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value); svg.append(node); return node; };
  for (let i = 0; i <= 4; i++) {
    const y = 185 - i * 42;
    line("line", {x1: 48, y1: y, x2: 790, y2: y, stroke: "#e7ebe9"});
    const label = line("text", {x: 42, y: y + 3, "text-anchor": "end", fill: "#7b8582", "font-size": 10});
    label.textContent = fmt(max * i / 4, 0);
  }
  const points = data.map((value, index) => `${48 + index * 742 / Math.max(1, data.length - 1)},${185 - value / max * 168}`).join(" ");
  if (data.length > 1) line("polyline", {points, fill: "none", stroke: "#c74646", "stroke-width": 2});
  data.forEach((value, index) => {
    if (data.length > 100 && index % 5) return;
    const dot = line("circle", {cx: 48 + index * 742 / Math.max(1, data.length - 1), cy: 185 - value / max * 168, r: 2.5, fill: "#c74646"});
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = `${index * step + 1}–${Math.min(rows.length, (index + 1) * step)}: ${fmt(value)} ${unit}`;
    dot.append(title);
  });
  const axis = line("text", {x: 790, y: 208, "text-anchor": "end", fill: "#7b8582", "font-size": 10});
  axis.textContent = `${rows.length} ${state.language === "zh" ? "条" : "runs"}`;
  target.append(svg);
}

function render() {
  const rows = visible(), graded = rows.filter(row => ["correct", "incorrect"].includes(row.grade));
  const correct = graded.filter(row => row.grade === "correct").length;
  text("count", `${report.completed} ${t("completed")} / ${report.total} ${t("total")}`);
  const cards = [
    [t("accuracy"), graded.length ? `${fmt(correct / graded.length * 100)}%` : "—", `${graded.length} ${t("graded")}`],
    [t("meanTokens"), fmt(average(rows.map(row => row.tokens))), `${rows.length} ${t("total")}`],
    [t("meanTime"), `${fmt(average(rows.map(row => row.seconds)))} s`, `${rows.length} ${t("total")}`],
    [t("meanCalls"), fmt(average(rows.map(row => row.calls))), `${rows.length} ${t("total")}`],
    [t("totalCalls"), fmt(rows.reduce((sum, row) => sum + (row.calls || 0), 0), 0), `${rows.length} ${t("total")}`]
  ];
  $("kpis").replaceChildren(...cards.map(([label, value, sub]) => { const node = document.createElement("div"); node.className = "kpi"; for (const [className, content] of [["label", label], ["value", value], ["sub", sub]]) { const part = document.createElement("div"); part.className = className; part.textContent = content; node.append(part); } return node; }));
  drawChart("token-chart", rows, "tokens", "token");
  drawChart("time-chart", rows, "seconds", "s");
  const pages = Math.max(1, Math.ceil(rows.length / 50));
  state.page = Math.min(state.page, pages - 1);
  text("table-count", `${rows.length} ${t("total")}`);
  text("page", `${state.page + 1} / ${pages}`);
  $("prev").disabled = state.page === 0;
  $("next").disabled = state.page >= pages - 1;
  const body = $("task-rows"); body.replaceChildren();
  for (const row of rows.slice(state.page * 50, (state.page + 1) * 50)) {
    const tr = document.createElement("tr");
    [`${row.task} · ${row.seed}`, t("grade")[row.grade] || row.grade, fmt(row.tokens, 0), `${fmt(row.seconds)} s`, fmt(row.calls, 0), fmt(row.changes, 0)].forEach(value => tr.append(cell(value)));
    tr.onclick = () => openDetail(row);
    body.append(tr);
  }
}

function openDetail(row) {
  $("detail").hidden = false;
  text("detail-title", `${row.task} · ${row.seed}`);
  text("prompt", t("loading"));
  $("detail").scrollIntoView({behavior: "smooth"});
  if (window.JEV_TASKS[row.key]) return renderDetail(window.JEV_TASKS[row.key]);
  const script = document.createElement("script");
  script.src = `data/tasks/${row.key}.js`;
  script.onload = () => renderDetail(window.JEV_TASKS[row.key]);
  script.onerror = () => text("prompt", t("failed"));
  document.body.append(script);
}

function renderDetail(detail) {
  state.detail = detail;
  text("prompt", detail.task);
  const run = detail.run;
  const stats = $("run-stats"); stats.replaceChildren();
  const node = document.createElement("div"); node.className = "run-card";
  node.textContent = `${t("grade")[run.grade] || run.grade} · ${fmt(run.generatedTokens, 0)} token · ${fmt(run.jevCalls, 0)} ${t("calls")} · ${run.stopReason || "—"}`;
  stats.append(node);
  const body = $("round-rows"); body.replaceChildren();
  for (const round of run.rounds) {
    const tr = document.createElement("tr");
    [Number(round.step) + 1, `${round.tokenStart ?? "—"}–${round.tokenEnd ?? "—"}`,
      `${fmt(round.scores.correctness, 2)} / ${fmt(round.utility, 2)}`,
      `${fmt(round.generationSeconds)} / ${fmt(round.jevSeconds)}`,
      round.action || "—", JSON.stringify(round.parameters)].forEach(value => tr.append(cell(value)));
    body.append(tr);
  }
  text("answer", run.finalAnswer || "—");
  text("path", run.resultPath);
}

function setLanguage(language) {
  state.language = language;
  if (window.updateBatchLabels) window.updateBatchLabels(language);
  document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  const mapping = {"nav-title": "nav", "all-batches": "allBatches", eyebrow: "eyebrow", intro: "intro", "filter-label": "filter", "search-label": "search", "charts-label": "charts", "token-title": "tokenTitle", "chart-note": "chartNote", "time-title": "timeTitle", "time-note": "timeNote", "table-label": "table", "task-title": "taskTitle", "task-note": "taskNote", "th-task": "task", "th-grade": "answer", "th-time": "time", "th-calls": "calls", "th-changes": "changes", prev: "prev", next: "next", "detail-label": "detail", close: "close", "round-title": "rounds", "th-round": "round", "th-score": "score", "th-round-time": "roundTime", "th-action": "action", "th-params": "params", "answer-label": "answerLabel", footnote: "footnote"};
  for (const [id, key] of Object.entries(mapping)) text(id, t(key));
  ["all", "correct", "incorrect", "ungraded"].forEach((key, index) => $("grade-filter").options[index].textContent = t("filters")[index]);
  text("batch-title", `${report.batch} · ${report.mode}`);
  text("batch-label", language === "zh" ? "实验批次" : "Experiment batch");
  $("zh").setAttribute("aria-pressed", String(language === "zh"));
  $("en").setAttribute("aria-pressed", String(language === "en"));
  try { localStorage.setItem("jev-dashboard-language", language); } catch (_) {}
  render();
  if (state.detail) renderDetail(state.detail);
}

$("grade-filter").onchange = event => { state.filter = event.target.value; state.page = 0; render(); };
$("search").oninput = event => { state.search = event.target.value.toLowerCase().trim(); state.page = 0; render(); };
$("prev").onclick = () => { state.page--; render(); };
$("next").onclick = () => { state.page++; render(); };
$("close").onclick = () => { $("detail").hidden = true; state.detail = null; };
$("zh").onclick = () => setLanguage("zh");
$("en").onclick = () => setLanguage("en");
setLanguage(state.language);
