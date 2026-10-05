"use strict";

/* Overview: accuracy against cost, paired comparison and the cost breakdown. */
(() => {
  const JD = window.JD;
  JD.extend({
    kpiAccuracy: "独立答案正确率", kpiAccuracySub: "Adaptive / 对照组", kpiAccuracyDiff: "正确率差", kpiAccuracyDiffSub: "配对差异，95% 区间",
    kpiToken: "平均生成 token 差", kpiTokenSub: "Adaptive − 对照组，95% 区间", kpiTime: "平均请求耗时差", kpiTimeSub: "生成 + Jev 请求，95% 区间",
    kpiJev: "Adaptive Jev 成本", gradedBoth: "道均可评分", tasksUnit: "道题", inputWord: "输入", outputWord: "输出",
    cardFrontier: "正确率 vs 平均生成 token", frontierX1: "平均生成 token", frontierX2: "平均生成 token + Jev 输入输出 token", frontierY: "正确率",
    cardTokenPair: "配对 token", cardTimePair: "配对请求耗时", logScale: "对数坐标", controlAxis: "对照组", adaptiveAxis: "Adaptive",
    outImproved: "Adaptive 改进", outRegressed: "Adaptive 退步", outSame: "结果相同或未评分",
    cardOutcome: "配对答案结果", rowControlCorrect: "对照 答对", rowControlWrong: "对照 答错", colAdaptiveCorrect: "Adaptive 答对", colAdaptiveWrong: "Adaptive 答错",
    mcnemar: "McNemar 精确检验 p", ungradedPairs: "未评分配对", accuracyWord: "正确率",
    cardCost: "成本分解", metric: "指标", delta: "Adaptive − 对照",
    mGenTokens: "生成 token", mGenSeconds: "生成耗时 (s)", mJevCalls: "Jev 请求数", mJevIn: "Jev 输入 token", mJevOut: "Jev 输出 token", mJevSeconds: "Jev 耗时 (s)",
    mTotalSeconds: "请求耗时 (s)", mRestarts: "重来次数", mWasted: "重来浪费 token", perTask: "每题均值（95% 区间）",
    cardStrata: "按对照组生成长度分层", strataBin: "对照组 token 区间", strataN: "题数", strataControl: "对照 token", strataAdaptive: "Adaptive token", strataDelta: "Δ token", strataAccC: "对照正确率", strataAccA: "Adaptive 正确率",
    noData: "没有数据", taskCount: "任务数", total: "合计", needPair: "此图比较对照组与 Adaptive，请在左侧同时勾选两者。", needAdaptive: "此页只含 Adaptive 的记录，请在左侧勾选 Adaptive。"
  }, {
    kpiAccuracy: "Independent answer accuracy", kpiAccuracySub: "Adaptive / control", kpiAccuracyDiff: "Accuracy difference", kpiAccuracyDiffSub: "Paired, 95% interval",
    kpiToken: "Mean generated-token difference", kpiTokenSub: "Adaptive − control, 95% interval", kpiTime: "Mean request-time difference", kpiTimeSub: "Generation + Jev, 95% interval",
    kpiJev: "Adaptive Jev cost", gradedBoth: "graded in both", tasksUnit: "tasks", inputWord: "input", outputWord: "output",
    cardFrontier: "Accuracy vs mean generated tokens", frontierX1: "mean generated tokens", frontierX2: "mean generated + Jev input/output tokens", frontierY: "accuracy",
    cardTokenPair: "Paired tokens", cardTimePair: "Paired request time", logScale: "log scale", controlAxis: "Control", adaptiveAxis: "Adaptive",
    outImproved: "Adaptive improved", outRegressed: "Adaptive regressed", outSame: "same or ungraded",
    cardOutcome: "Paired answer outcomes", rowControlCorrect: "Control correct", rowControlWrong: "Control wrong", colAdaptiveCorrect: "Adaptive correct", colAdaptiveWrong: "Adaptive wrong",
    mcnemar: "McNemar exact p", ungradedPairs: "Ungraded pairs", accuracyWord: "Accuracy",
    cardCost: "Cost breakdown", metric: "Metric", delta: "Adaptive − control",
    mGenTokens: "Generated tokens", mGenSeconds: "Generation time (s)", mJevCalls: "Jev requests", mJevIn: "Jev input tokens", mJevOut: "Jev output tokens", mJevSeconds: "Jev time (s)",
    mTotalSeconds: "Request time (s)", mRestarts: "Restarts", mWasted: "Tokens wasted in restarts", perTask: "Per-task mean (95% interval)",
    cardStrata: "By control generation length", strataBin: "Control tokens", strataN: "Tasks", strataControl: "Control tokens", strataAdaptive: "Adaptive tokens", strataDelta: "Δ tokens", strataAccC: "Control accuracy", strataAccA: "Adaptive accuracy",
    noData: "No data", taskCount: "Tasks", total: "Total", needPair: "This chart compares the control with adaptive; tick both runs on the left.", needAdaptive: "This tab only holds adaptive records; tick Adaptive on the left."
  });

  const finite = values => values.filter(Number.isFinite);
  const interval = (values, digits = 0, signed = false) => {
    const clean = finite(values);
    if (!clean.length) return "—";
    const mean = JD.mean(clean), [low, high] = JD.bootstrap(clean);
    const f = value => signed ? JD.signed(value, digits) : JD.fmt(value, digits);
    return low == null ? f(mean) : `${f(mean)} [${f(low)}, ${f(high)}]`;
  };
  const gradeValue = grade => grade === "correct" ? 1 : grade === "incorrect" ? 0 : null;

  function kpi(label, value, sub) {
    const node = JD.el("div", null, "kpi");
    node.append(JD.el("div", label, "kpi-label"), JD.el("div", value, "kpi-value"), JD.el("div", sub, "kpi-sub"));
    return node;
  }

  function render() {
    const host = JD.$("tab-overview"), rows = JD.rows(), control = JD.state.control;
    host.replaceChildren();
    const pairs = rows.map(row => ({row, c: row.modes[control], a: row.modes.adaptive}));
    const graded = pairs.filter(pair => JD.graded(pair.c.grade) && JD.graded(pair.a.grade));
    const cOk = graded.filter(pair => pair.c.grade === "correct").length, aOk = graded.filter(pair => pair.a.grade === "correct").length;
    const diffs = graded.map(pair => gradeValue(pair.a.grade) - gradeValue(pair.c.grade));
    const accuracyDiff = diffs.length ? JD.mean(diffs) * 100 : null;
    const [accLow, accHigh] = JD.bootstrap(diffs);
    const tokenDiffs = finite(pairs.map(pair => pair.a.generatedTokens - pair.c.generatedTokens));
    const timeDiffs = finite(pairs.map(pair => JD.requestSeconds(pair.a) - JD.requestSeconds(pair.c)));
    const calls = pairs.reduce((sum, pair) => sum + (pair.a.jevCalls || 0), 0);
    const jevIn = pairs.reduce((sum, pair) => sum + (pair.a.jevInputTokens || 0), 0), jevOut = pairs.reduce((sum, pair) => sum + (pair.a.jevOutputTokens || 0), 0);
    const strip = JD.el("div", null, "kpis");
    if (!JD.pairOn()) strip.replaceChildren(JD.notice(JD.t("needPair")));
    else strip.append(
      kpi(JD.t("kpiAccuracy"), graded.length ? `${JD.fmt(aOk / graded.length * 100)}% / ${JD.fmt(cOk / graded.length * 100)}%` : "—", `${JD.t("kpiAccuracySub")} · ${graded.length} ${JD.t("gradedBoth")}`),
      kpi(JD.t("kpiAccuracyDiff"), accuracyDiff == null ? "—" : `${JD.signed(accuracyDiff, 1)} pp`, accLow == null ? JD.t("kpiAccuracyDiffSub") : `[${JD.signed(accLow * 100, 1)}, ${JD.signed(accHigh * 100, 1)}] pp`),
      kpi(JD.t("kpiToken"), JD.signed(JD.mean(tokenDiffs), 0), `${interval(tokenDiffs, 0, true)}`),
      kpi(JD.t("kpiTime"), `${JD.signed(JD.mean(timeDiffs), 1)} s`, `${interval(timeDiffs, 1, true)}`),
      kpi(JD.t("kpiJev"), `${JD.fmt(calls, 0)} calls`, `${JD.fmt(jevIn, 0)} ${JD.t("inputWord")} / ${JD.fmt(jevOut, 0)} ${JD.t("outputWord")} tokens`)
    );
    const grid = JD.el("div", null, "cards");
    host.append(strip, grid);

    /* accuracy against cost, every visible mode with 95% intervals */
    const choose = document.createElement("select");
    choose.className = "mini-select";
    choose.append(Object.assign(document.createElement("option"), {value: "gen", textContent: JD.t("frontierX1")}), Object.assign(document.createElement("option"), {value: "all", textContent: JD.t("frontierX2")}));
    const frontier = JD.card(JD.t("cardFrontier"), {controls: choose});
    const drawFrontier = () => {
      const W = 560, H = 320, m = {l: 58, r: 20, t: 16, b: 44};
      const root = JD.canvas(W, H), items = [];
      for (const mode of JD.modes.filter(name => JD.state.visible[name])) {
        const tokens = [], marks = [];
        for (const row of rows) {
          const run = row.modes[mode];
          if (!run || !Number.isFinite(run.generatedTokens)) continue;
          tokens.push(run.generatedTokens + (choose.value === "all" ? (run.jevInputTokens || 0) + (run.jevOutputTokens || 0) : 0));
          const value = gradeValue(run.grade);
          if (value != null) marks.push(value);
        }
        if (!tokens.length || !marks.length) continue;
        items.push({mode, x: JD.mean(tokens), xi: JD.bootstrap(tokens), y: JD.mean(marks), yi: JD.bootstrap(marks), n: marks.length});
      }
      if (!items.length) { root.append(JD.label(W / 2, H / 2, JD.t("noData"), {anchor: "middle", size: 13})); frontier.body.replaceChildren(root); return; }
      const xmin = Math.min(...items.map(item => item.xi[0] ?? item.x)), xmax = Math.max(...items.map(item => item.xi[1] ?? item.x));
      const ymin = Math.min(...items.map(item => item.yi[0] ?? item.y)), ymax = Math.max(...items.map(item => item.yi[1] ?? item.y));
      const xs = (xmax - xmin) * 0.25 || xmax * 0.1 || 1, ys = (ymax - ymin) * 0.25 || 0.05;
      const x0 = Math.max(0, xmin - xs), x1 = xmax + xs, y0 = Math.max(0, ymin - ys), y1 = Math.min(1, ymax + ys);
      const X = JD.linear(x0, x1, m.l, W - m.r), Y = JD.linear(y0, y1, H - m.b, m.t);
      JD.axes(root, m, W, H, X, Y, JD.niceTicks(x0, x1, 5), JD.niceTicks(y0, y1, 5), {xLabel: choose.value === "all" ? JD.t("frontierX2") : JD.t("frontierX1"), yLabel: JD.t("frontierY"), yFormat: value => `${JD.fmt(value * 100, 0)}%`});
      for (const item of items) {
        const color = JD.COLOR[item.mode];
        if (item.xi[0] != null) root.append(JD.S("line", {x1: X(item.xi[0]), x2: X(item.xi[1]), y1: Y(item.y), y2: Y(item.y), stroke: color, "stroke-width": 1.6}));
        if (item.yi[0] != null) root.append(JD.S("line", {x1: X(item.x), x2: X(item.x), y1: Y(item.yi[0]), y2: Y(item.yi[1]), stroke: color, "stroke-width": 1.6}));
        const dot = JD.S("circle", {cx: X(item.x), cy: Y(item.y), r: 6, fill: color});
        dot.addEventListener("mousemove", event => JD.tip.show(`<div class="tip-title">${JD.mode(item.mode)}</div><div>${JD.t("frontierY")}: <b>${JD.pct(item.y)}</b> <span>n=${item.n}</span></div><div>${JD.t("frontierX1")}: <b>${JD.fmt(item.x, 0)}</b></div>`, event));
        dot.addEventListener("mouseleave", () => JD.tip.hide());
        const leftSide = items.indexOf(item) % 2 === 0;
        root.append(dot, JD.label(X(item.x) + (leftSide ? -9 : 9), Y(item.y) - 9, JD.mode(item.mode), {fill: color, size: 12, weight: "600", anchor: leftSide ? "end" : "start"}));
      }
      frontier.body.replaceChildren(root);
      frontier.csvRows = () => [["mode", "n", "accuracy", "accuracy_low", "accuracy_high", "mean_tokens", "tokens_low", "tokens_high"], ...items.map(item => [item.mode, item.n, item.y, item.yi[0], item.yi[1], item.x, item.xi[0], item.xi[1]])];
    };
    choose.onchange = drawFrontier;
    drawFrontier();
    grid.append(frontier);

    /* paired scatters */
    const scatterCard = (title, value, unit) => {
      const log = Object.assign(document.createElement("input"), {type: "checkbox", checked: true});
      const wrap = JD.el("label", null, "mini-check");
      wrap.append(log, document.createTextNode(JD.t("logScale")));
      const node = JD.card(title, {controls: wrap});
      const draw = () => {
        if (!JD.pairOn()) { node.body.replaceChildren(JD.notice(JD.t("needPair"))); node.csvRows = null; return; }
        const points = pairs.map(pair => ({row: pair.row, x: value(pair.c), y: value(pair.a), color: JD.COLOR.adaptive}));
        node.body.replaceChildren(JD.scatter({points, xLabel: `${JD.t("controlAxis")}${unit}`, yLabel: `${JD.t("adaptiveAxis")}${unit}`, diagonal: true, log: log.checked, annotate: 3}));
        node.csvRows = () => [["task", "control", "adaptive"], ...points.map(point => [point.row.task, point.x, point.y])];
      };
      log.onchange = draw;
      draw();
      return node;
    };
    grid.append(scatterCard(JD.t("cardTokenPair"), run => run.generatedTokens, " (token)"), scatterCard(JD.t("cardTimePair"), JD.requestSeconds, " (s)"));

    /* 2×2 outcome table with the exact McNemar test */
    const both = graded.filter(pair => pair.c.grade === "correct" && pair.a.grade === "correct").length;
    const fixedOnly = graded.filter(pair => pair.c.grade === "correct" && pair.a.grade === "incorrect").length;
    const adaptiveOnly = graded.filter(pair => pair.c.grade === "incorrect" && pair.a.grade === "correct").length;
    const neither = graded.length - both - fixedOnly - adaptiveOnly;
    const outcome = JD.card(JD.t("cardOutcome"));
    if (!JD.pairOn()) outcome.body.append(JD.notice(JD.t("needPair")));
    else {
      outcome.body.append(JD.table(["", JD.t("colAdaptiveCorrect"), JD.t("colAdaptiveWrong"), JD.t("total")],
        [[JD.t("rowControlCorrect"), both, fixedOnly, both + fixedOnly], [JD.t("rowControlWrong"), adaptiveOnly, neither, adaptiveOnly + neither], ["", both + adaptiveOnly, fixedOnly + neither, graded.length]], {align: ["", "r", "r", "r"]}));
      const facts = JD.el("div", null, "facts");
      facts.append(JD.el("span", `${JD.t("mcnemar")} = ${graded.length ? JD.fmt(JD.mcnemar(fixedOnly, adaptiveOnly), 3) : "—"}`), JD.el("span", `${JD.t("ungradedPairs")}: ${pairs.length - graded.length}`));
      outcome.body.append(facts);
    }
    outcome.csvRows = () => [["control", "adaptive_correct", "adaptive_wrong"], ["correct", both, fixedOnly], ["wrong", adaptiveOnly, neither]];
    grid.append(outcome);

    /* cost breakdown, per-task means with 95% intervals */
    const metrics = [
      ["mGenTokens", run => run.generatedTokens, 0], ["mGenSeconds", run => run.generationSeconds, 1], ["mJevCalls", run => run.jevCalls, 1],
      ["mJevIn", run => run.jevInputTokens, 0], ["mJevOut", run => run.jevOutputTokens, 0], ["mJevSeconds", run => run.jevSeconds, 1],
      ["mTotalSeconds", JD.requestSeconds, 1], ["mRestarts", run => run.restarts, 2], ["mWasted", run => run.wastedTokens, 0]
    ];
    const shown = JD.modes.filter(mode => JD.state.visible[mode]);
    const cost = JD.card(JD.t("cardCost"), {wide: true});
    const costRows = metrics.map(([key, getter, digits]) => [JD.t(key), ...shown.map(mode => interval(pairs.map(pair => getter(mode === "adaptive" ? pair.a : pair.row.modes[mode] || {})), digits)),
      JD.pairOn() ? interval(pairs.map(pair => getter(pair.a) - getter(pair.c)), digits, true) : "—"]);
    cost.body.append(JD.el("div", JD.t("perTask"), "table-note"), JD.table([JD.t("metric"), ...shown.map(JD.mode), JD.t("delta")], costRows, {align: ["", ...shown.map(() => "r"), "r"]}));
    cost.csvRows = () => [[JD.t("metric"), ...shown.map(JD.mode), JD.t("delta")], ...costRows];
    grid.append(cost);

    /* strata by control generation length */
    const bins = [[0, 1500], [1500, 2500], [2500, 4000], [4000, Infinity]];
    const strataRows = bins.map(([low, high]) => {
      const group = pairs.filter(pair => pair.c.generatedTokens >= low && pair.c.generatedTokens < high);
      const gradedGroup = group.filter(pair => JD.graded(pair.c.grade) && JD.graded(pair.a.grade));
      const share = side => gradedGroup.length ? JD.pct(gradedGroup.filter(pair => pair[side].grade === "correct").length / gradedGroup.length) : "—";
      return [high === Infinity ? `≥ ${low}` : `${low} – ${high}`, group.length, JD.fmt(JD.mean(finite(group.map(pair => pair.c.generatedTokens))), 0), JD.fmt(JD.mean(finite(group.map(pair => pair.a.generatedTokens))), 0),
        JD.signed(JD.mean(finite(group.map(pair => pair.a.generatedTokens - pair.c.generatedTokens))), 0), share("c"), share("a")];
    });
    const strata = JD.card(JD.t("cardStrata"), {wide: true});
    const strataHead = [JD.t("strataBin"), JD.t("strataN"), JD.t("strataControl"), JD.t("strataAdaptive"), JD.t("strataDelta"), JD.t("strataAccC"), JD.t("strataAccA")];
    strata.body.append(JD.pairOn() ? JD.table(strataHead, strataRows, {align: ["", "r", "r", "r", "r", "r", "r"]}) : JD.notice(JD.t("needPair")));
    strata.csvRows = () => [strataHead, ...strataRows];
    grid.append(strata);
  }

  JD.register("overview", render);
})();
