"use strict";

/* Tasks (TensorBoard "HParams"): every task as a line across its run-level metrics, a sortable table, and a per-task drawer. */
(() => {
  const JD = window.JD;
  JD.extend({
    cardParallel: "任务总览（平行坐标）", axisControlTok: "对照 token", axisAdaptiveTok: "Adaptive token", axisDelta: "Δ token", axisChanges: "实际参数变更", axisRestarts: "重来次数", axisCalls: "Adaptive Jev 调用",
    cardTable: "任务明细", thTask: "任务 / 种子", thControlAnswer: "对照答案", thAdaptiveAnswer: "Adaptive 答案", thDeltaToken: "Δ token", thDeltaTime: "Δ 请求耗时", thCalls: "Adaptive Jev 调用", thChanges: "实际参数变更", thRestarts: "重来",
    prev: "上一页", next: "下一页", close: "关闭", prompt: "题目", reference: "参考答案", finalAnswer: "最终答案末段", resultPath: "结果文件", stopReason: "停止原因",
    gradeCorrect: "正确", gradeIncorrect: "错误", gradeUngraded: "未评分", runCardTokens: "生成 token", runCardSeconds: "请求耗时", runCardCalls: "Jev 调用", runCardRounds: "轮", runCardChanges: "实际变更", runCardRestarts: "重来",
    outImproved: "Adaptive 改进", outRegressed: "Adaptive 退步", outSame: "结果相同或未评分", tag: "标签", loadFail: "无法读取该任务的数据文件。", noData: "没有数据", segmentWord: "段"
  }, {
    cardParallel: "Tasks overview (parallel coordinates)", axisControlTok: "Control tokens", axisAdaptiveTok: "Adaptive tokens", axisDelta: "Δ tokens", axisChanges: "Applied changes", axisRestarts: "Restarts", axisCalls: "Adaptive Jev calls",
    cardTable: "Task details", thTask: "Task / seed", thControlAnswer: "Control answer", thAdaptiveAnswer: "Adaptive answer", thDeltaToken: "Δ tokens", thDeltaTime: "Δ request time", thCalls: "Adaptive Jev calls", thChanges: "Applied changes", thRestarts: "Restarts",
    prev: "Previous", next: "Next", close: "Close", prompt: "Task", reference: "Reference answer", finalAnswer: "Final-answer excerpt", resultPath: "Result file", stopReason: "Stop reason",
    gradeCorrect: "Correct", gradeIncorrect: "Incorrect", gradeUngraded: "Ungraded", runCardTokens: "generated tokens", runCardSeconds: "request time", runCardCalls: "Jev calls", runCardRounds: "rounds", runCardChanges: "applied changes", runCardRestarts: "restarts",
    outImproved: "Adaptive improved", outRegressed: "Adaptive regressed", outSame: "same or ungraded", tag: "Tag", loadFail: "Could not load this task's data file.", noData: "No data", segmentWord: "segment"
  });
  const gradeText = grade => JD.t(grade === "correct" ? "gradeCorrect" : grade === "incorrect" ? "gradeIncorrect" : "gradeUngraded");
  const PAGE = 50;
  let page = 0, sortKey = "delta", sortDirection = -1;

  function metrics(row) {
    const control = row.modes[JD.state.control], adaptive = row.modes.adaptive;
    return {
      row, control, adaptive, controlTokens: control.generatedTokens, adaptiveTokens: adaptive.generatedTokens, delta: adaptive.generatedTokens - control.generatedTokens,
      deltaTime: JD.requestSeconds(adaptive) - JD.requestSeconds(control), calls: adaptive.jevCalls, changes: adaptive.executedChanges, restarts: adaptive.restarts || 0
    };
  }
  const outcomeColor = item => !JD.pairOn() ? (JD.on("adaptive") ? JD.COLOR.adaptive : JD.COLOR[JD.state.control]) : item.control.grade === "incorrect" && item.adaptive.grade === "correct" ? JD.COLOR.adaptive : item.control.grade === "correct" && item.adaptive.grade === "incorrect" ? JD.COLOR.wrong : "#b6bdc1";

  function parallelCard(items) {
    const axes = [["axisControlTok", "controlTokens", "c"], ["axisAdaptiveTok", "adaptiveTokens", "a"], ["axisDelta", "delta", "ca"], ["axisChanges", "changes", "a"], ["axisRestarts", "restarts", "a"], ["axisCalls", "calls", "a"]]
      .filter(([, , needs]) => (!needs.includes("c") || JD.on(JD.state.control)) && (!needs.includes("a") || JD.on("adaptive")));
    const card = JD.card(JD.t("cardParallel"), {wide: true});
    if (axes.length < 2) { card.body.append(JD.notice(JD.t("needPair"))); return card; }
    const W = 1100, H = 340, m = {l: 50, r: 50, t: 46, b: 34};
    const root = JD.canvas(W, H);
    /* heavy-tailed axes use a signed log scale so a single long run does not flatten everything else */
    const symlog = value => Math.sign(value) * Math.log10(1 + Math.abs(value));
    const scale = axes.map(([, key]) => {
      const values = items.map(item => item[key]).filter(Number.isFinite);
      const low = Math.min(...values), high = Math.max(...values);
      const bent = ["controlTokens", "adaptiveTokens", "delta", "calls"].includes(key);
      const map = bent ? symlog : value => value;
      return {key, low, high, bent, map, y: JD.linear(map(low), map(high) === map(low) ? map(low) + 1 : map(high), H - m.b, m.t)};
    });
    const X = index => m.l + (W - m.l - m.r) * index / (axes.length - 1);
    axes.forEach(([name], index) => {
      root.append(JD.S("line", {x1: X(index), x2: X(index), y1: m.t, y2: H - m.b, stroke: "#b5b5b5"}));
      root.append(JD.label(X(index), m.t - 22, JD.t(name), {anchor: "middle", fill: "#222", size: 12, weight: "600"}));
      root.append(JD.label(X(index), m.t - 8, JD.fmt(scale[index].high, 0), {anchor: "middle", size: 10.5}));
      root.append(JD.label(X(index), H - m.b + 16, JD.fmt(scale[index].low, 0), {anchor: "middle", size: 10.5}));
      if (scale[index].low < 0 && scale[index].high > 0) {
        root.append(JD.S("line", {x1: X(index) - 4, x2: X(index) + 4, y1: scale[index].y(scale[index].map(0)), y2: scale[index].y(scale[index].map(0)), stroke: "#555"}));
        root.append(JD.label(X(index) + 7, scale[index].y(scale[index].map(0)) + 4, "0", {size: 10.5}));
      }
    });
    const order = items.slice().sort((a, b) => (outcomeColor(a) === "#b6bdc1" ? 0 : 1) - (outcomeColor(b) === "#b6bdc1" ? 0 : 1));
    const legend = JD.pairOn() ? [{name: JD.t("outImproved"), color: JD.COLOR.adaptive}, {name: JD.t("outRegressed"), color: JD.COLOR.wrong}, {name: JD.t("outSame"), color: "#b6bdc1"}]
      : [{name: JD.mode(JD.on("adaptive") ? "adaptive" : JD.state.control), color: outcomeColor(items[0] || {})}];
    for (const item of order) {
      const points = scale.map((axis, index) => Number.isFinite(item[axis.key]) ? `${X(index)},${axis.y(axis.map(item[axis.key]))}` : null);
      if (points.includes(null)) continue;
      const line = JD.S("polyline", {points: points.join(" "), fill: "none", stroke: outcomeColor(item), "stroke-width": 1.3, "stroke-opacity": 0.55, class: "pc-line"});
      line.addEventListener("mousemove", event => JD.tip.show(`<div class="tip-title">${JD.escape(item.row.task)}</div><div>Δ: <b>${JD.signed(item.delta, 0)}</b></div>`, event));
      line.addEventListener("mouseleave", () => JD.tip.hide());
      line.addEventListener("click", () => JD.openTask(item.row));
      root.append(line);
    }
    card.body.append(root, JD.legend(legend));
    card.csvRows = () => [["task", ...axes.map(([, key]) => key)], ...items.map(item => [item.row.task, ...axes.map(([, key]) => item[key])])];
    return card;
  }

  function tableCard(items) {
    const card = JD.card(JD.t("cardTable"), {wide: true});
    const c = JD.on(JD.state.control), a = JD.on("adaptive");
    const columns = [
      ["task", "thTask", item => `${item.row.task} · ${item.row.seed}`, false, true], ["controlGrade", "thControlAnswer", item => gradeText(item.control.grade), false, c],
      ["adaptiveGrade", "thAdaptiveAnswer", item => gradeText(item.adaptive.grade), false, a], ["delta", "thDeltaToken", item => JD.signed(item.delta, 0), true, c && a],
      ["deltaTime", "thDeltaTime", item => `${JD.signed(item.deltaTime, 1)} s`, true, c && a], ["calls", "thCalls", item => JD.fmt(item.calls, 0), true, a],
      ["changes", "thChanges", item => JD.fmt(item.changes, 0), true, a], ["restarts", "thRestarts", item => JD.fmt(item.restarts, 0), true, a]
    ].filter(column => column[4]);
    if (!columns.some(column => column[0] === sortKey)) sortKey = columns[0][0];
    const value = (item, key) => key === "task" ? item.row.task : key === "controlGrade" ? item.control.grade : key === "adaptiveGrade" ? item.adaptive.grade : item[key];
    const holder = JD.el("div");
    const draw = () => {
      const sorted = items.slice().sort((a, b) => {
        const x = value(a, sortKey), y = value(b, sortKey);
        if (x == null || Number.isNaN(x)) return 1;
        if (y == null || Number.isNaN(y)) return -1;
        return (x < y ? -1 : x > y ? 1 : 0) * sortDirection;
      });
      const pages = Math.max(1, Math.ceil(sorted.length / PAGE));
      page = Math.min(page, pages - 1);
      const table = document.createElement("table");
      const head = document.createElement("tr");
      columns.forEach(([key, name, , numeric]) => {
        const th = JD.el("th", JD.t(name) + (sortKey === key ? (sortDirection < 0 ? " ↓" : " ↑") : ""), numeric ? "num sortable" : "sortable");
        th.onclick = () => { if (sortKey === key) sortDirection = -sortDirection; else { sortKey = key; sortDirection = key === "task" ? 1 : -1; } draw(); };
        head.append(th);
      });
      const thead = document.createElement("thead"), tbody = document.createElement("tbody");
      thead.append(head);
      for (const item of sorted.slice(page * PAGE, (page + 1) * PAGE)) {
        const tr = document.createElement("tr");
        tr.className = "clickable";
        columns.forEach(([key, , text, numeric]) => {
          const td = JD.el("td", text(item), numeric ? "num" : "");
          if (key === "adaptiveGrade" && item.adaptive.grade === "correct" && item.control.grade === "incorrect") td.classList.add("good");
          if (key === "adaptiveGrade" && item.adaptive.grade === "incorrect" && item.control.grade === "correct") td.classList.add("bad");
          tr.append(td);
        });
        tr.onclick = () => JD.openTask(item.row);
        tbody.append(tr);
      }
      table.append(thead, tbody);
      const scroll = JD.el("div", null, "table-scroll");
      scroll.append(table);
      const pager = JD.el("div", null, "pager");
      const prev = JD.el("button", JD.t("prev"), "icon-btn"), next = JD.el("button", JD.t("next"), "icon-btn");
      prev.type = next.type = "button";
      prev.disabled = page === 0; next.disabled = page >= pages - 1;
      prev.onclick = () => { page--; draw(); }; next.onclick = () => { page++; draw(); };
      pager.append(prev, JD.el("span", `${page + 1} / ${pages} · ${sorted.length}`), next);
      holder.replaceChildren(scroll, pager);
    };
    draw();
    card.body.append(holder);
    card.csvRows = () => [columns.map(([, name]) => JD.t(name)), ...items.map(item => columns.map(([, , text]) => text(item)))];
    return card;
  }

  function render() {
    const host = JD.$("tab-tasks");
    const items = JD.rows().map(metrics);
    const grid = JD.el("div", null, "cards");
    grid.append(parallelCard(items), tableCard(items));
    host.replaceChildren(grid);
  }
  JD.register("tasks", render);

  /* ---- the drawer ---- */
  let drawerTag = "trouble";
  function openDrawer(row) {
    const drawer = JD.$("drawer");
    drawer.hidden = false;
    drawer.replaceChildren(JD.el("div", `${row.task} · seed ${row.seed}`, "drawer-title"));
    const close = () => { drawer.hidden = true; document.removeEventListener("keydown", onKey); };
    const onKey = event => { if (event.key === "Escape") close(); };
    document.addEventListener("keydown", onKey);
    JD.loadDetails([row]).then(() => {
      const detail = JD.detail(row);
      if (!detail) { drawer.replaceChildren(JD.el("div", JD.t("loadFail"), "status")); return; }
      const head = JD.el("div", null, "drawer-head");
      const closeButton = JD.el("button", JD.t("close"), "icon-btn");
      closeButton.type = "button"; closeButton.onclick = close;
      head.append(JD.el("h2", `${row.task} · seed ${row.seed}`), closeButton);
      const prompt = JD.el("div", null, "drawer-block");
      prompt.append(JD.el("h4", JD.t("prompt")), JD.el("p", detail.prompt, "prompt"));
      if (detail.reference) prompt.append(JD.el("h4", JD.t("reference")), JD.el("p", String(detail.reference).split("####").pop().trim(), "prompt"));
      const cards = JD.el("div", null, "run-cards");
      for (const mode of JD.modes) {
        const run = detail.modes[mode];
        if (!run) continue;
        const node = JD.el("div", null, "run-card");
        node.append(JD.el("strong", JD.mode(mode)), JD.el("div", `${gradeText(run.grade)} · ${JD.fmt(run.generatedTokens, 0)} ${JD.t("runCardTokens")}`),
          JD.el("div", `${JD.fmt(JD.requestSeconds(run))} s ${JD.t("runCardSeconds")} · ${run.jevCalls} ${JD.t("runCardCalls")}`),
          JD.el("div", `${run.rounds.length} ${JD.t("runCardRounds")} · ${run.executedChanges} ${JD.t("runCardChanges")} · ${run.restarts || 0} ${JD.t("runCardRestarts")} · ${JD.t("stopReason")}: ${run.stopReason || "—"}`));
        cards.append(node);
      }
      const tags = JD.tagList([row]);
      const select = document.createElement("select");
      select.className = "mini-select";
      for (const tag of tags) select.append(Object.assign(document.createElement("option"), {value: tag.id, textContent: JD.tagTitle(tag)}));
      select.value = tags.some(tag => tag.id === drawerTag) ? drawerTag : tags[0].id;
      const chartCard = JD.card(JD.t("tag"), {controls: select});
      const draw = () => {
        drawerTag = select.value;
        const tag = tags.find(item => item.id === select.value);
        chartCard.titleNode.textContent = JD.tagTitle(tag);
        const series = JD.modes.filter(mode => detail.modes[mode] && JD.on(mode)).map(mode => ({
          name: JD.mode(mode), color: JD.COLOR[mode], dash: JD.DASH[mode],
          ...JD.smoothPoints(JD.path(detail.modes[mode]).map((round, index) => ({x: index + 1, y: tag.get(round), n: null})).filter(point => Number.isFinite(point.y)))
        }));
        chartCard.body.replaceChildren(JD.lineChart({series, xLabel: JD.t("segmentWord"), yMin: tag.group === "scores" ? 0 : null, yMax: tag.group === "scores" ? 1 : null, H: 260}), JD.legend(series.filter(item => item.points.length).map(item => ({name: item.name, color: item.color, dash: item.dash}))));
        chartCard.csvRows = () => JD.seriesCsv(series, JD.t("segmentWord"));
      };
      select.onchange = draw;
      draw();
      JD.drawerRedraw = draw;
      const answers = JD.el("div", null, "drawer-block");
      for (const mode of JD.modes) {
        const run = detail.modes[mode];
        if (!run) continue;
        answers.append(JD.el("h4", `${JD.mode(mode)} · ${JD.t("finalAnswer")}`), JD.el("pre", run.finalAnswer || "(empty)"), JD.el("small", `${JD.t("resultPath")}: ${run.resultPath}`));
      }
      drawer.replaceChildren(head, prompt, cards, chartCard, answers);
      drawer.scrollTop = 0;
    });
  }
  JD.tabs.tasks.open = openDrawer;
})();
