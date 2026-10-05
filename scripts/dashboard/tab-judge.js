"use strict";

/* Judge: how well the Jev scores track what happens.  Behavior: what Jev did with the parameters. */
(() => {
  const JD = window.JD;
  JD.extend({
    tabJudgeTitle: "评委", tabBehaviorTitle: "决策",
    cardCalibration: "校准", noJudge: "这批运行用的是旧评分方案，没有 on_track 和症状评分，评委页没有数据。", calibSegment: "取第几段", calibLast: "最后一段", calibMode: "运行",
    calibRate: "答对比例", calibBin: "分数区间", calibN: "题数", calibAuc: "AUC",
    cardOnTrackCurve: "随段变化（按最终对错）", curveCorrect: "最终答对", curveWrong: "最终答错",
    cardFlagged: "症状严重度 ≥ 0.5 的轮次占比", flaggedRounds: "轮",
    cardDirections: "各参数的调整方向", dirUp: "上调", dirDown: "下调", dirOther: "切换或设值",
    cardAsked: "各参数被询问与被调整", askedShare: "被调整占被询问的比例",
    cardFirstChange: "首次调参出现在第几段", firstNone: "全程未调整", segmentLabel: n => `第 ${n} 段`,
    cardByTrouble: "调参率（按当轮 trouble 分组）", cardByWorst: "调参率（按当轮最严重症状分组）", changeRate: "下一轮有调整的比例",
    cardRestarts: "发生重来的任务", rsTask: "任务", rsRestarts: "重来次数", rsWasted: "浪费 token", rsControlTok: "对照 token", rsAdaptiveTok: "Adaptive token", rsControlGrade: "对照答案", rsAdaptiveGrade: "Adaptive 答案",
    gradeCorrect: "正确", gradeIncorrect: "错误", gradeUngraded: "未评分", noRestarts: "这批没有重来", noData: "没有数据"
  }, {
    tabJudgeTitle: "Judge", tabBehaviorTitle: "Behavior",
    cardCalibration: "calibration", noJudge: "This batch used the old scoring design: no on_track and no symptom scores, so the Judge tab has no data.", calibSegment: "Segment", calibLast: "last segment", calibMode: "Run",
    calibRate: "share correct", calibBin: "score bin", calibN: "tasks", calibAuc: "AUC",
    cardOnTrackCurve: "by segment, split by final outcome", curveCorrect: "finally correct", curveWrong: "finally wrong",
    cardFlagged: "Rounds with symptom severity ≥ 0.5", flaggedRounds: "rounds",
    cardDirections: "Direction of each parameter change", dirUp: "up", dirDown: "down", dirOther: "switch or set",
    cardAsked: "Parameters asked about and changed", askedShare: "changed / asked",
    cardFirstChange: "Segment of the first parameter change", firstNone: "never changed", segmentLabel: n => `segment ${n}`,
    cardByTrouble: "Change rate by trouble of the round", cardByWorst: "Change rate by worst symptom of the round", changeRate: "share with a change next round",
    cardRestarts: "Tasks with restarts", rsTask: "Task", rsRestarts: "Restarts", rsWasted: "Wasted tokens", rsControlTok: "Control tokens", rsAdaptiveTok: "Adaptive tokens", rsControlGrade: "Control answer", rsAdaptiveGrade: "Adaptive answer",
    gradeCorrect: "Correct", gradeIncorrect: "Incorrect", gradeUngraded: "Ungraded", noRestarts: "No restarts in this batch", noData: "No data"
  });

  const SYMPTOMS = ["scatter", "rigidity", "distortion", "over_checking", "under_checking"];
  const gradeText = grade => JD.t(grade === "correct" ? "gradeCorrect" : grade === "incorrect" ? "gradeIncorrect" : "gradeUngraded");

  /* ---------------- Judge ---------------- */
  function bootstrapAuc(items) {
    const positive = items.filter(item => item.ok).map(item => item.p), negative = items.filter(item => !item.ok).map(item => item.p);
    const value = JD.auc(positive, negative);
    if (value == null) return [null, null, null];
    let seed = 99;
    const next = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
    const draws = [];
    for (let round = 0; round < 400; round++) {
      const sample = items.map(() => items[Math.floor(next() * items.length)]);
      const auc = JD.auc(sample.filter(item => item.ok).map(item => item.p), sample.filter(item => !item.ok).map(item => item.p));
      if (auc != null) draws.push(auc);
    }
    draws.sort((a, b) => a - b);
    return [value, JD.quantile(draws, 0.025), JD.quantile(draws, 0.975)];
  }

  function calibrationCard(rows, forecast) {
    const segment = document.createElement("select"), mode = document.createElement("select");
    segment.className = mode.className = "mini-select";
    for (const value of ["1", "2", "3", "5", "8", "last"]) segment.append(Object.assign(document.createElement("option"), {value, textContent: value === "last" ? JD.t("calibLast") : `${JD.t("calibSegment")} ${value}`}));
    segment.value = "3";
    for (const name of ["fixed", "adaptive"]) if (JD.modes.includes(name) && JD.on(name)) mode.append(Object.assign(document.createElement("option"), {value: name, textContent: JD.mode(name)}));
    mode.value = JD.on("adaptive") ? "adaptive" : mode.value;
    const controls = JD.el("span", null, "inline-controls");
    controls.append(mode, segment);
    const card = JD.card(`${forecast} ${JD.t("cardCalibration")}`, {controls});
    const draw = () => {
      const items = [];
      for (const row of rows) {
        const detail = JD.detail(row), run = detail && detail.modes[mode.value];
        if (!run) continue;
        const path = JD.path(run), round = segment.value === "last" ? path[path.length - 1] : path[Number(segment.value) - 1];
        const p = round && round.scores ? round.scores[forecast] : null, grade = run.grade;
        if (Number.isFinite(p) && JD.graded(grade)) items.push({p, ok: grade === "correct", row});
      }
      const W = 560, H = 300, m = {l: 54, r: 16, t: 14, b: 46};
      const root = JD.canvas(W, H);
      const bins = [0, 0.2, 0.4, 0.6, 0.8, 1.0000001].map((low, index, edges) => index < 5 ? {low, high: edges[index + 1]} : null).filter(Boolean);
      const X = JD.linear(0, 1, m.l, W - m.r), Y = JD.linear(0, 1, H - m.b, m.t);
      JD.axes(root, m, W, H, X, Y, [0, 0.2, 0.4, 0.6, 0.8, 1], [0, 0.25, 0.5, 0.75, 1], {xLabel: forecast, yLabel: JD.t("calibRate"), xFormat: value => JD.fmt(value, 1), yFormat: value => `${JD.fmt(value * 100, 0)}%`});
      root.append(JD.S("line", {x1: X(0), y1: Y(0), x2: X(1), y2: Y(1), stroke: "#999", "stroke-dasharray": "5 4"}));
      const table = [];
      for (const bin of bins) {
        const group = items.filter(item => item.p >= bin.low && item.p < bin.high);
        table.push([`${JD.fmt(bin.low, 1)}–${JD.fmt(Math.min(1, bin.high), 1)}`, group.length, group.length ? group.filter(item => item.ok).length / group.length : null]);
        if (!group.length) continue;
        const rate = group.filter(item => item.ok).length / group.length;
        const rect = JD.S("rect", {x: X(bin.low) + 3, y: Y(rate), width: X(Math.min(1, bin.high)) - X(bin.low) - 6, height: H - m.b - Y(rate), fill: JD.COLOR.adaptive, "fill-opacity": 0.8});
        rect.addEventListener("mousemove", event => JD.tip.show(`<div>${JD.t("calibBin")}: <b>${JD.fmt(bin.low, 1)}–${JD.fmt(Math.min(1, bin.high), 1)}</b></div><div>${JD.t("calibRate")}: <b>${JD.pct(rate, 0)}</b> <span>${JD.t("calibN")}=${group.length}</span></div>`, event));
        rect.addEventListener("mouseleave", () => JD.tip.hide());
        root.append(rect, JD.label((X(bin.low) + X(Math.min(1, bin.high))) / 2, Y(rate) - 5, `n=${group.length}`, {anchor: "middle", size: 10}));
      }
      const [auc, low, high] = bootstrapAuc(items);
      const facts = JD.el("div", null, "facts");
      facts.append(JD.el("span", `${JD.t("calibAuc")} ${auc == null ? "—" : `${JD.fmt(auc, 2)} [${JD.fmt(low, 2)}, ${JD.fmt(high, 2)}]`}`), JD.el("span", `${JD.t("calibN")}: ${items.length}`));
      card.body.replaceChildren(root, facts);
      card.csvRows = () => [["task", forecast, "correct"], ...items.map(item => [item.row.task, item.p, item.ok ? 1 : 0])];
    };
    segment.onchange = mode.onchange = draw;
    draw();
    return card;
  }

  function onTrackCurveCard(rows, forecast) {
    const mode = document.createElement("select");
    mode.className = "mini-select";
    for (const name of ["fixed", "adaptive"]) if (JD.modes.includes(name) && JD.on(name)) mode.append(Object.assign(document.createElement("option"), {value: name, textContent: JD.mode(name)}));
    mode.value = JD.on("adaptive") ? "adaptive" : mode.value;
    const card = JD.card(`${forecast} ${JD.t("cardOnTrackCurve")}`, {controls: mode});
    const draw = () => {
      const split = {correct: [], incorrect: []};
      for (const row of rows) {
        const detail = JD.detail(row), run = detail && detail.modes[mode.value];
        if (run && split[run.grade]) split[run.grade].push(run);
      }
      const series = [["correct", JD.t("curveCorrect"), JD.COLOR.correct], ["incorrect", JD.t("curveWrong"), JD.COLOR.wrong]].map(([key, name, color]) => {
        const columns = JD.aggregate(split[key], round => (round.scores || {})[forecast]);
        return {name: `${name} (${split[key].length})`, color, ...JD.smoothPoints(columns.map(column => ({x: column.x, y: column.mean, n: column.n,
          bands: JD.state.bands.judge ? [[column.mean - 1.96 * column.se, column.mean + 1.96 * column.se]] : undefined})))};
      });
      card.body.replaceChildren(JD.lineChart({series, xLabel: JD.t("segmentWord"), yMin: 0, yMax: 1}), JD.legend(series.map(item => ({name: item.name, color: item.color}))));
      card.csvRows = () => JD.seriesCsv(series, JD.t("segmentWord"));
    };
    mode.onchange = draw;
    draw();
    return card;
  }

  function flaggedCard(rows, symptoms) {
    const card = JD.card(JD.t("cardFlagged"));
    const shown = ["fixed", "adaptive"].filter(mode => JD.modes.includes(mode) && JD.state.visible[mode]);
    const groups = symptoms.map(name => ({label: name, bars: shown.map(mode => {
      let total = 0, hit = 0;
      for (const row of rows) {
        const detail = JD.detail(row);
        if (!detail || !detail.modes[mode]) continue;
        for (const round of JD.path(detail.modes[mode])) {
          const value = (round.scores || {})[name];
          if (Number.isFinite(value)) { total++; hit += value >= 0.5; }
        }
      }
      return {name: JD.mode(mode), color: JD.COLOR[mode], value: total ? hit / total : null, note: `${hit}/${total} ${JD.t("flaggedRounds")}`};
    })}));
    card.body.append(JD.bars({groups, xMax: 1, format: value => JD.pct(value, 0), labelWidth: 130}), JD.legend(shown.map(mode => ({name: JD.mode(mode), color: JD.COLOR[mode]}))));
    card.csvRows = () => [["symptom", "mode", "share", "note"], ...groups.flatMap(group => group.bars.map(bar => [group.label, bar.name, bar.value, bar.note]))];
    return card;
  }

  function renderJudge() {
    const host = JD.$("tab-judge");
    JD.withDetails(host, rows => {
      if (!JD.on("fixed") && !JD.on("adaptive")) { host.replaceChildren(JD.notice(JD.t("needAdaptive"))); return; }
      /* batches made before the symptom scores have no on_track; their correctness score plays the same role */
      const recorded = new Set(JD.tagList(rows).filter(tag => tag.group === "scores").map(tag => tag.name));
      const forecast = ["on_track", "correctness"].find(name => recorded.has(name));
      const symptoms = SYMPTOMS.filter(name => recorded.has(name));
      if (!forecast && !symptoms.length) { host.replaceChildren(JD.notice(JD.t("noJudge"))); return; }
      const grid = JD.el("div", null, "cards");
      if (forecast) grid.append(calibrationCard(rows, forecast), onTrackCurveCard(rows, forecast));
      if (symptoms.length) grid.append(flaggedCard(rows, symptoms));
      host.replaceChildren(grid);
    });
  }
  JD.register("judge", renderJudge);

  /* ---------------- Behavior ---------------- */
  const changeKind = (before, after) => typeof before === "number" && typeof after === "number" ? (after > before ? "up" : "down") : "other";

  function directionCard(rows) {
    const counts = {};
    for (const row of rows) {
      const detail = JD.detail(row);
      if (!detail) continue;
      const path = JD.path(detail.modes.adaptive);
      for (let index = 1; index < path.length; index++) {
        const before = path[index - 1].parameters || {}, after = path[index].parameters || {};
        for (const name of Object.keys(after)) {
          if (JSON.stringify(before[name]) === JSON.stringify(after[name])) continue;
          const entry = counts[name] = counts[name] || {up: 0, down: 0, other: 0};
          entry[changeKind(before[name], after[name])]++;
        }
      }
    }
    const names = Object.keys(counts).sort((a, b) => Object.values(counts[b]).reduce((s, v) => s + v, 0) - Object.values(counts[a]).reduce((s, v) => s + v, 0));
    const card = JD.card(JD.t("cardDirections"));
    const groups = names.map(name => ({label: name, bars: [
      {name: JD.t("dirUp"), color: JD.COLOR.adaptive, value: counts[name].up}, {name: JD.t("dirDown"), color: JD.COLOR.fixed, value: counts[name].down}, {name: JD.t("dirOther"), color: "#c9ced1", value: counts[name].other}]}));
    card.body.append(groups.length ? JD.bars({groups, rowHeight: 34, labelWidth: 170}) : JD.el("div", JD.t("noData"), "status"),
      JD.legend([{name: JD.t("dirUp"), color: JD.COLOR.adaptive}, {name: JD.t("dirDown"), color: JD.COLOR.fixed}, {name: JD.t("dirOther"), color: "#c9ced1"}]));
    card.csvRows = () => [["parameter", "up", "down", "other"], ...names.map(name => [name, counts[name].up, counts[name].down, counts[name].other])];
    return card;
  }

  function askedCard() {
    const activity = JD.overview.parameterActivity || {};
    const items = Object.entries(activity).filter(([, v]) => v[0] > 0).map(([name, [asked, changed]]) => ({name, asked, changed, rate: changed / asked})).sort((a, b) => b.rate - a.rate || b.asked - a.asked);
    const card = JD.card(JD.t("cardAsked"));
    card.body.append(items.length ? JD.bars({groups: items.map(item => ({label: item.name, bars: [{name: JD.t("askedShare"), color: JD.COLOR.adaptive, value: item.rate, note: `${item.changed}/${item.asked}`}]})), xMax: 1, format: value => JD.pct(value, 0), labelWidth: 190, rowHeight: 24}) : JD.el("div", JD.t("noData"), "status"));
    card.csvRows = () => [["parameter", "asked", "changed"], ...items.map(item => [item.name, item.asked, item.changed])];
    return card;
  }

  function firstChangeCard(rows) {
    const counts = {};
    let never = 0;
    for (const row of rows) {
      const detail = JD.detail(row);
      if (!detail) continue;
      const path = JD.path(detail.modes.adaptive);
      let first = null;
      for (let index = 1; index < path.length && first == null; index++) if (JSON.stringify(path[index - 1].parameters) !== JSON.stringify(path[index].parameters)) first = index + 1;
      if (first == null) never++; else counts[first] = (counts[first] || 0) + 1;
    }
    const keys = Object.keys(counts).map(Number).sort((a, b) => a - b);
    const groups = [...keys.map(key => ({label: JD.t("segmentLabel")(key), bars: [{name: JD.t("calibN"), color: JD.COLOR.adaptive, value: counts[key]}]})), {label: JD.t("firstNone"), bars: [{name: JD.t("calibN"), color: "#c9ced1", value: never}]}];
    const card = JD.card(JD.t("cardFirstChange"));
    card.body.append(JD.bars({groups, rowHeight: 26, labelWidth: 120}));
    card.csvRows = () => [["segment", "tasks"], ...keys.map(key => [key, counts[key]]), ["never", never]];
    return card;
  }

  function rateCard(rows, title, groupOf, labels) {
    const stats = {};
    for (const row of rows) {
      const detail = JD.detail(row);
      if (!detail) continue;
      const path = JD.path(detail.modes.adaptive);
      path.slice(0, -1).forEach(round => {
        const key = groupOf(round);
        if (key == null) return;
        const entry = stats[key] = stats[key] || {n: 0, changed: 0};
        entry.n++; entry.changed += round.executedNextRound ? 1 : 0;
      });
    }
    const card = JD.card(title);
    const groups = labels.filter(([key]) => stats[key]).map(([key, text]) => ({label: text, bars: [{name: JD.t("changeRate"), color: JD.COLOR.adaptive, value: stats[key].changed / stats[key].n, note: `${stats[key].changed}/${stats[key].n}`}]}));
    card.body.append(groups.length ? JD.bars({groups, xMax: 1, format: value => JD.pct(value, 0), labelWidth: 150, rowHeight: 30}) : JD.el("div", JD.t("noData"), "status"));
    card.csvRows = () => [["group", "changed", "rounds"], ...labels.filter(([key]) => stats[key]).map(([key, text]) => [text, stats[key].changed, stats[key].n])];
    return card;
  }

  function restartCard(rows) {
    const items = rows.filter(row => (row.modes.adaptive.restarts || 0) > 0);
    const card = JD.card(JD.t("cardRestarts"), {wide: true});
    const control = JD.state.control;
    const body = items.map(row => {
      const link = JD.el("button", row.task, "link");
      link.type = "button"; link.onclick = () => JD.openTask(row);
      return [link, row.modes.adaptive.restarts, JD.fmt(row.modes.adaptive.wastedTokens, 0), JD.fmt(row.modes[control].generatedTokens, 0), JD.fmt(row.modes.adaptive.generatedTokens, 0), gradeText(row.modes[control].grade), gradeText(row.modes.adaptive.grade)];
    });
    const head = [JD.t("rsTask"), JD.t("rsRestarts"), JD.t("rsWasted"), JD.t("rsControlTok"), JD.t("rsAdaptiveTok"), JD.t("rsControlGrade"), JD.t("rsAdaptiveGrade")];
    card.body.append(items.length ? JD.table(head, body, {align: ["", "r", "r", "r", "r", "", ""]}) : JD.el("div", JD.t("noRestarts"), "status"));
    card.csvRows = () => [head, ...items.map(row => [row.task, row.modes.adaptive.restarts, row.modes.adaptive.wastedTokens, row.modes[control].generatedTokens, row.modes.adaptive.generatedTokens, row.modes[control].grade, row.modes.adaptive.grade])];
    return card;
  }

  function renderBehavior() {
    const host = JD.$("tab-behavior");
    JD.withDetails(host, rows => {
      if (!JD.on("adaptive")) { host.replaceChildren(JD.notice(JD.t("needAdaptive"))); return; }
      const grid = JD.el("div", null, "cards");
      const bands = [[0, "0 – 0.25"], [1, "0.25 – 0.5"], [2, "0.5 – 0.75"], [3, "0.75 – 1"]];
      grid.append(directionCard(rows), askedCard(), firstChangeCard(rows),
        rateCard(rows, JD.t("cardByTrouble"), round => Number.isFinite(round.trouble) ? Math.min(3, Math.floor(round.trouble * 4)) : null, bands),
        rateCard(rows, JD.t("cardByWorst"), round => round.worst || null, SYMPTOMS.map(name => [name, name])),
        restartCard(rows));
      host.replaceChildren(grid);
    });
  }
  JD.register("behavior", renderBehavior);
})();
