"use strict";

/* Shell: tab bar, left settings column, language. Everything else lives in the tab modules. */
(() => {
  const JD = window.JD;
  JD.extend({
    siteTitle: "实验探索", tabOverview: "总览", tabCurves: "曲线", tabDistributions: "分布", tabJudge: "评委", tabBehavior: "决策", tabTasks: "任务",
    sideBatch: "实验批次", sideControl: "对照组", sideFilter: "答案筛选", sideSearch: "搜索任务", sideRuns: "运行", sideSmoothing: "平滑", sideBand: "显示 95% 范围带",
    controlBaseline: "Baseline · 仅 Qwen", controlFixed: "Fixed · Jev 评分", all: "全部", improved: "Adaptive 改进", regressed: "Adaptive 退步", ungraded: "未评分",
    pairedTasks: "配对任务", runsWord: "条运行记录"
  }, {
    siteTitle: "Experiment explorer", tabOverview: "Overview", tabCurves: "Curves", tabDistributions: "Distributions", tabJudge: "Judge", tabBehavior: "Behavior", tabTasks: "Tasks",
    sideBatch: "Experiment batch", sideControl: "Control", sideFilter: "Answer filter", sideSearch: "Search tasks", sideRuns: "Runs", sideSmoothing: "Smoothing", sideBand: "Show 95% band",
    controlBaseline: "Baseline · Qwen only", controlFixed: "Fixed · Jev scoring", all: "All", improved: "Adaptive improved", regressed: "Adaptive regressed", ungraded: "Ungraded",
    pairedTasks: "paired tasks", runsWord: "runs"
  });

  function applyText() {
    document.documentElement.lang = JD.state.language === "zh" ? "zh-CN" : "en";
    document.title = `Jev · ${JD.t("siteTitle")}`;
    document.querySelectorAll("[data-i18n]").forEach(node => { node.textContent = JD.t(node.dataset.i18n); });
    JD.$("lang-zh").setAttribute("aria-pressed", String(JD.state.language === "zh"));
    JD.$("lang-en").setAttribute("aria-pressed", String(JD.state.language === "en"));
    const batch = (window.batchTime && window.batchTime(JD.overview.batch)) || JD.overview.batch || "";
    JD.$("dataset-count").textContent = `${batch} · ${JD.tasks.length} ${JD.t("pairedTasks")} · ${JD.tasks.length * JD.modes.length} ${JD.t("runsWord")}`;
    const toggles = JD.$("run-toggles");
    toggles.replaceChildren();
    for (const mode of JD.modes) {
      const label = document.createElement("label");
      const box = Object.assign(document.createElement("input"), {type: "checkbox", checked: JD.state.visible[mode]});
      box.onchange = () => { JD.state.visible[mode] = box.checked; JD.invalidate(); };
      const swatch = JD.el("i", null, "swatch");
      swatch.style.background = JD.COLOR[mode];
      label.append(box, swatch, document.createTextNode(JD.mode(mode)));
      toggles.append(label);
    }
  }
  function setLanguage(language) {
    JD.state.language = language;
    try { localStorage.setItem("jev-dashboard-language", language); } catch (_) {}
    if (window.updateBatchLabels) window.updateBatchLabels(language);
    applyText();
    JD.invalidate();
  }

  JD.$("lang-zh").onclick = () => setLanguage("zh");
  JD.$("lang-en").onclick = () => setLanguage("en");
  JD.$("control").onchange = event => { JD.state.control = event.target.value; JD.invalidate(); };
  JD.$("control").querySelectorAll("option").forEach(option => { option.hidden = !JD.modes.includes(option.value); });
  JD.$("control").value = JD.state.control;
  JD.$("grade-filter").onchange = event => { JD.state.filter = event.target.value; JD.invalidate(); };
  let searchTimer = null;
  JD.$("search").oninput = event => { JD.state.search = event.target.value.trim(); clearTimeout(searchTimer); searchTimer = setTimeout(JD.invalidate, 200); };
  JD.$("smoothing").oninput = event => {
    JD.state.smoothing = Number(event.target.value);
    JD.$("smoothing-value").textContent = JD.state.smoothing.toFixed(2);
    JD.redrawLines();
  };
  JD.$("show-band").onchange = event => { JD.state.bands[JD.state.tab] = event.target.checked; JD.redrawLines(); };
  document.querySelectorAll(".tab-btn").forEach(button => {
    button.onclick = () => { location.hash = button.dataset.tab; };
  });
  const fromHash = () => {
    const id = location.hash.replace("#", "");
    JD.show(JD.tabs[id] ? id : "overview");
  };
  window.addEventListener("hashchange", fromHash);
  applyText();
  fromHash();
})();
