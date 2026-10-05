"use strict";

/* Curves (TensorBoard "Scalars") and Distributions: every per-segment quantity, aggregated over the selected tasks. */
(() => {
  const JD = window.JD;
  const MIN_N = 3;
  JD.extend({
    tabCurvesTitle: "曲线", filterTags: "筛选标签（支持正则）", expandAll: "全部展开", collapseAll: "全部收起", loadingRounds: "正在读取逐轮记录",
    groupScores: "症状与预测", groupCost: "成本", groupParameters: "采样参数", segmentWord: "段",
    cardDeltaHist: "Δ token 分布（Adaptive − 对照）", markMean: "均值", markMedian: "中位数", distBands: "中位数 · 25–75% · 10–90%",
    "tag.trouble": "症状总量 trouble", "tag.scatter": "散乱 scatter", "tag.rigidity": "僵住 rigidity", "tag.distortion": "扭曲 distortion",
    "tag.over_checking": "过度复核 over_checking", "tag.under_checking": "复核不足 under_checking", "tag.on_track": "在正轨 on_track",
    "tag.cumulativeTokens": "累计 token", "tag.segmentTokens": "每段 token", "tag.generationSeconds": "生成耗时 (s)", "tag.jevSeconds": "Jev 耗时 (s)", "tag.jevInputTokens": "Jev 输入 token",
    noTags: "没有匹配的标签", noData: "没有数据"
  }, {
    tabCurvesTitle: "Curves", filterTags: "Filter tags (regex supported)", expandAll: "Expand all", collapseAll: "Collapse all", loadingRounds: "Loading round records",
    groupScores: "Symptoms & forecast", groupCost: "Cost", groupParameters: "Sampling parameters", segmentWord: "segment",
    cardDeltaHist: "Δ tokens (adaptive − control)", markMean: "mean", markMedian: "median", distBands: "median · 25–75% · 10–90%",
    "tag.trouble": "trouble (largest symptom)", "tag.scatter": "scatter", "tag.rigidity": "rigidity", "tag.distortion": "distortion",
    "tag.over_checking": "over_checking", "tag.under_checking": "under_checking", "tag.on_track": "on_track",
    "tag.cumulativeTokens": "cumulative tokens", "tag.segmentTokens": "tokens per segment", "tag.generationSeconds": "generation time (s)", "tag.jevSeconds": "Jev time (s)", "tag.jevInputTokens": "Jev input tokens",
    noTags: "No matching tags", noData: "No data"
  });

  /* Values at each segment position over runs that reach it (position = index along the answered attempt). */
  JD.aggregate = (runs, getter) => {
    const columns = [];
    for (const run of runs) JD.path(run).forEach((round, index) => {
      const value = getter(round);
      if (Number.isFinite(value)) (columns[index] = columns[index] || []).push(value);
    });
    const out = [];
    columns.forEach((values, index) => {
      if (!values || values.length < MIN_N) return;
      const sorted = values.slice().sort((a, b) => a - b);
      out.push({x: index + 1, n: values.length, mean: JD.mean(values), se: JD.sd(values) / Math.sqrt(values.length), sorted});
    });
    return out;
  };
  const modesToDraw = () => JD.modes.filter(mode => JD.state.visible[mode]);

  function meanSeries(rows, tag) {
    return modesToDraw().map(mode => {
      const columns = JD.aggregate(rows.map(row => JD.detail(row)).filter(Boolean).map(detail => detail.modes[mode]).filter(Boolean), tag.get);
      const smoothed = JD.smoothPoints(columns.map(column => ({x: column.x, y: column.mean, n: column.n,
        bands: JD.state.bands.curves ? [[column.mean - 1.96 * column.se, column.mean + 1.96 * column.se]] : undefined})));
      return {name: JD.mode(mode), color: JD.COLOR[mode], dash: JD.DASH[mode], ...smoothed};
    });
  }
  function bandSeries(rows, tag) {
    return modesToDraw().map(mode => {
      const columns = JD.aggregate(rows.map(row => JD.detail(row)).filter(Boolean).map(detail => detail.modes[mode]).filter(Boolean), tag.get);
      const smoothed = JD.smoothPoints(columns.map(column => ({x: column.x, y: JD.quantile(column.sorted, 0.5), n: column.n,
        bands: JD.state.bands.distributions ? [[JD.quantile(column.sorted, 0.1), JD.quantile(column.sorted, 0.9)], [JD.quantile(column.sorted, 0.25), JD.quantile(column.sorted, 0.75)]] : undefined})));
      return {name: JD.mode(mode), color: JD.COLOR[mode], dash: JD.DASH[mode], ...smoothed};
    });
  }
  const isUnit = tag => tag.group === "scores";

  function tagCard(rows, tag, builder) {
    const card = JD.card(JD.tagTitle(tag));
    card.titleNode.title = tag.id;
    const series = builder(rows, tag);
    card.body.append(JD.lineChart({series, xLabel: JD.t("segmentWord"), yMin: isUnit(tag) ? 0 : null, yMax: isUnit(tag) ? 1 : null, yFormat: value => JD.fmt(value, isUnit(tag) ? 2 : 1)}));
    card.body.append(JD.legend(series.filter(item => item.points.length).map(item => ({name: item.name, color: item.color, dash: item.dash}))));
    card.csvRows = () => JD.seriesCsv(series, JD.t("segmentWord"));
    return card;
  }

  /* shared page skeleton: waits for the per-round files, then draws */
  function withDetails(host, draw) {
    const rows = JD.rows();
    const status = JD.el("div", `${JD.t("loadingRounds")} 0 / ${rows.length}`, "status");
    host.replaceChildren(status);
    const ticket = host.ticket = (host.ticket || 0) + 1;
    JD.loadDetails(rows, (done, total) => { status.textContent = `${JD.t("loadingRounds")} ${done} / ${total}`; }).then(() => { if (host.ticket === ticket) draw(rows); });
  }

  JD.withDetails = withDetails;

  /* ---- Curves ---- */
  let curvesFilter = "";
  function renderCurves() {
    const host = JD.$("tab-curves");
    withDetails(host, rows => {
      const tags = JD.tagList(rows);
      const bar = JD.el("div", null, "tag-bar");
      const input = Object.assign(document.createElement("input"), {type: "search", placeholder: JD.t("filterTags"), value: curvesFilter, spellcheck: false});
      const open = JD.el("button", JD.t("expandAll"), "icon-btn"), close = JD.el("button", JD.t("collapseAll"), "icon-btn");
      open.type = close.type = "button";
      bar.append(input, open, close);
      const holder = JD.el("div", null, "groups");
      host.replaceChildren(bar, holder);
      const draw = () => {
        curvesFilter = input.value;
        let match = () => true;
        if (curvesFilter) { try { const pattern = new RegExp(curvesFilter, "i"); match = tag => pattern.test(tag.id) || pattern.test(JD.tagTitle(tag)); } catch (_) { const needle = curvesFilter.toLowerCase(); match = tag => tag.id.toLowerCase().includes(needle); } }
        holder.replaceChildren();
        for (const [group, key] of [["scores", "groupScores"], ["cost", "groupCost"], ["parameters", "groupParameters"]]) {
          const members = tags.filter(tag => tag.group === group && match(tag));
          if (!members.length) continue;
          const section = document.createElement("details");
          section.open = group !== "parameters" || !!curvesFilter;
          const summary = document.createElement("summary");
          summary.append(JD.el("span", JD.t(key)), JD.el("em", `${members.length}`));
          const cards = JD.el("div", null, "cards");
          members.forEach(tag => cards.append(tagCard(rows, tag, meanSeries)));
          section.append(summary, cards);
          holder.append(section);
        }
        if (!holder.children.length) holder.append(JD.el("div", JD.t("noTags"), "status"));
      };
      input.oninput = draw;
      open.onclick = () => holder.querySelectorAll("details").forEach(node => { node.open = true; });
      close.onclick = () => holder.querySelectorAll("details").forEach(node => { node.open = false; });
      draw();
    });
  }
  JD.register("curves", renderCurves);

  /* ---- Distributions ---- */
  function renderDistributions() {
    const host = JD.$("tab-distributions");
    withDetails(host, rows => {
      const control = JD.state.control;
      const deltas = rows.map(row => row.modes.adaptive.generatedTokens - row.modes[control].generatedTokens).filter(Number.isFinite);
      const holder = JD.el("div", null, "groups");
      host.replaceChildren(holder);
      const hist = JD.card(JD.t("cardDeltaHist"), {wide: true});
      const mean = JD.mean(deltas), median = JD.median(deltas), [low, high] = JD.bootstrap(deltas);
      if (!JD.pairOn()) hist.body.append(JD.notice(JD.t("needPair")));
      else hist.body.append(JD.histogram({values: deltas, band: [low, high], xLabel: `${JD.t("strataDelta")}`, W: 1100, H: 320, markers: [
        {x: mean, color: JD.COLOR.adaptive, label: `${JD.t("markMean")} ${JD.signed(mean, 0)}`}, {x: median, color: JD.COLOR.wrong, dash: "4 3", label: `${JD.t("markMedian")} ${JD.signed(median, 0)}`}]}));
      hist.csvRows = () => [["task", "delta_tokens"], ...rows.map(row => [row.task, row.modes.adaptive.generatedTokens - row.modes[control].generatedTokens])];
      const tags = JD.tagList(rows).filter(tag => tag.group !== "parameters");
      const grid = JD.el("div", null, "cards");
      grid.append(hist);
      for (const tag of tags) {
        const card = tagCard(rows, tag, bandSeries);
        card.titleNode.append(JD.el("small", JD.t("distBands"), "sub"));
        grid.append(card);
      }
      holder.append(grid);
    });
  }
  JD.register("distributions", renderDistributions);
})();
