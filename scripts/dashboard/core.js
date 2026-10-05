"use strict";

/* Shared state, statistics and chart primitives for the explorer tabs.
   The layout follows TensorBoard: a top tab bar, a left settings column and cards that each hold one
   chart or table with SVG / CSV download. Every chart is plain SVG so a downloaded file looks the same anywhere. */
(() => {
  const overview = window.JEV_OVERVIEW;
  const modes = overview.modes || ["baseline", "fixed", "adaptive"];
  const JD = window.JD = {
    overview, modes, tasks: overview.tasks, tabs: {}, copy: {zh: {}, en: {}},
    COLOR: {baseline: "#9aa3a8", fixed: "#4f5d66", adaptive: "#1f6fb5", correct: "#7c8587", wrong: "#c0392b"},
    DASH: {baseline: "4 3", fixed: "", adaptive: ""},
    state: {
      language: "zh", tab: "overview", control: modes.includes("baseline") ? "baseline" : "fixed", filter: "all", search: "",
      visible: Object.fromEntries(modes.map(mode => [mode, true])), smoothing: 0, bands: {curves: false, distributions: true, judge: false}
    }
  };
  try { JD.state.language = localStorage.getItem("jev-dashboard-language") === "en" ? "en" : "zh"; } catch (_) {}
  const NS = "http://www.w3.org/2000/svg";
  const INK = "#222", MUTED = "#6b6b6b", AXIS = "#b5b5b5", GRID = "#ececec";
  const FONT = "Inter, 'Segoe UI', 'Microsoft YaHei', sans-serif";

  /* ---- text ---- */
  JD.extend = (zh, en) => { Object.assign(JD.copy.zh, zh); Object.assign(JD.copy.en, en); };
  JD.t = key => JD.copy[JD.state.language][key] ?? key;
  JD.mode = mode => ({baseline: "Baseline", fixed: "Fixed", adaptive: "Adaptive"})[mode] || mode;

  /* ---- small helpers ---- */
  JD.$ = id => document.getElementById(id);
  JD.el = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  };
  JD.fmt = (value, digits = 1) => {
    if (value == null || !Number.isFinite(Number(value))) return "—";
    const text = Number(value).toLocaleString("en-US", {maximumFractionDigits: digits});
    return /^-0(\.0*)?$/.test(text) ? text.slice(1) : text;
  };
  JD.signed = (value, digits = 0) => value == null || !Number.isFinite(value) ? "—"
    : `${value > 0 ? "+" : value < 0 ? "−" : ""}${JD.fmt(Math.abs(value), digits)}`;
  JD.pct = (value, digits = 1) => value == null || !Number.isFinite(value) ? "—" : `${JD.fmt(value * 100, digits)}%`;
  JD.shortId = task => String(task).replace(/^.*_/, "");
  JD.S = (tag, attributes = {}, text) => {
    const node = document.createElementNS(NS, tag);
    for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, String(value));
    if (text != null) node.textContent = text;
    return node;
  };
  const S = JD.S;
  const label = (x, y, text, {size = 11, fill = MUTED, anchor = "start", weight = "400"} = {}) =>
    S("text", {x, y, "font-size": size, fill, "text-anchor": anchor, "font-weight": weight, "font-family": FONT}, text);
  JD.label = label;
  JD.linear = (d0, d1, r0, r1) => value => r0 + (value - d0) / ((d1 - d0) || 1) * (r1 - r0);
  JD.niceTicks = (low, high, count = 5) => {
    const span = (high - low) || 1, raw = span / count, power = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map(m => m * power).find(s => s >= raw);
    const ticks = [];
    for (let value = Math.ceil(low / step - 1e-9) * step; value <= high + step * 1e-9; value += step) ticks.push(Math.round(value / step * 1e6) / 1e6 * step);
    return ticks;
  };

  /* ---- statistics ---- */
  JD.mean = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  JD.sd = values => {
    if (values.length < 2) return 0;
    const m = JD.mean(values);
    return Math.sqrt(values.reduce((sum, value) => sum + (value - m) ** 2, 0) / (values.length - 1));
  };
  JD.quantile = (sorted, q) => {
    if (!sorted.length) return null;
    const position = (sorted.length - 1) * q, low = Math.floor(position), high = Math.ceil(position);
    return sorted[low] + (sorted[high] - sorted[low]) * (position - low);
  };
  JD.median = values => JD.quantile(values.slice().sort((a, b) => a - b), 0.5);
  function random(seed) {
    let a = seed >>> 0;
    return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ t >>> 15, t | 1); t ^= t + Math.imul(t ^ t >>> 7, t | 61); return ((t ^ t >>> 14) >>> 0) / 4294967296; };
  }
  /* 95% percentile bootstrap interval of any statistic of a sample (seeded, so the page never flickers). */
  JD.bootstrap = (values, statistic = JD.mean, rounds = 1000) => {
    if (values.length < 2) return [null, null];
    const next = random(12345), draws = [];
    for (let round = 0; round < rounds; round++) {
      const sample = new Array(values.length);
      for (let index = 0; index < values.length; index++) sample[index] = values[Math.floor(next() * values.length)];
      draws.push(statistic(sample));
    }
    draws.sort((a, b) => a - b);
    return [JD.quantile(draws, 0.025), JD.quantile(draws, 0.975)];
  };
  /* Exact two-sided McNemar test from the two discordant counts. */
  JD.mcnemar = (b, c) => {
    const n = b + c;
    if (!n) return 1;
    const k = Math.min(b, c);
    let term = Math.pow(0.5, n), tail = 0;
    for (let i = 0; i <= k; i++) { tail += term; term *= (n - i) / (i + 1); }
    return Math.min(1, 2 * tail);
  };
  /* Area under the ROC curve (Mann–Whitney): chance that a positive scores above a negative. */
  JD.auc = (positive, negative) => {
    if (!positive.length || !negative.length) return null;
    let wins = 0;
    for (const p of positive) for (const n of negative) wins += p > n ? 1 : p === n ? 0.5 : 0;
    return wins / (positive.length * negative.length);
  };

  /* ---- the run checkboxes: a chart that compares two runs needs both of them on ---- */
  JD.on = mode => !!JD.state.visible[mode];
  JD.pairOn = () => JD.on(JD.state.control) && JD.on("adaptive");
  JD.notice = (text, wide = false) => JD.el("div", text, "status");

  /* ---- selection ---- */
  JD.rows = () => {
    const {search, filter, control} = JD.state;
    let match = null;
    if (search) {
      try { const pattern = new RegExp(search, "i"); match = text => pattern.test(text); }
      catch (_) { const needle = search.toLowerCase(); match = text => text.toLowerCase().includes(needle); }
    }
    return JD.tasks.filter(task => {
      const c = task.modes[control].grade, a = task.modes.adaptive.grade;
      if (match && !match(task.task)) return false;
      if (filter === "improved" && !(c === "incorrect" && a === "correct")) return false;
      if (filter === "regressed" && !(c === "correct" && a === "incorrect")) return false;
      if (filter === "ungraded" && c !== "ungraded" && a !== "ungraded") return false;
      return true;
    });
  };
  JD.graded = grade => grade === "correct" || grade === "incorrect";
  JD.requestSeconds = run => Number.isFinite(run.generationSeconds) && Number.isFinite(run.jevSeconds) ? run.generationSeconds + run.jevSeconds : null;
  /* The rounds of the attempt that produced the answer (restarted attempts are dropped). */
  JD.path = run => (run.rounds || []).filter(round => !round.abandoned);

  /* ---- per-round records are loaded lazily, one small script per task ---- */
  JD.loadDetails = (rows, onProgress) => new Promise(resolve => {
    const pending = rows.filter(row => !window.JEV_TASKS[row.key]);
    const total = pending.length;
    if (!total) { resolve(); return; }
    let index = 0, active = 0, done = 0;
    const next = () => {
      while (active < 8 && index < total) {
        const row = pending[index++];
        active++;
        const script = document.createElement("script");
        script.src = `data/tasks/${row.key}.js`;
        const finish = () => { active--; done++; if (onProgress) onProgress(done, total); if (done === total) resolve(); else next(); };
        script.onload = finish; script.onerror = finish;
        document.body.append(script);
      }
    };
    next();
  });
  JD.detail = row => window.JEV_TASKS[row.key];

  /* ---- scalar tags: everything recorded per segment ---- */
  const SCORE_ORDER = ["scatter", "rigidity", "distortion", "over_checking", "under_checking", "on_track"];
  JD.tagList = rows => {
    const scoreNames = new Set(), parameterNames = [];
    for (const row of rows) {
      const detail = JD.detail(row);
      if (!detail) continue;
      for (const run of Object.values(detail.modes)) for (const round of run.rounds || []) {
        for (const name of Object.keys(round.scores || {})) scoreNames.add(name);
        for (const name of Object.keys(round.parameters || {})) if (!parameterNames.includes(name)) parameterNames.push(name);
      }
    }
    const scores = [...SCORE_ORDER.filter(name => scoreNames.has(name)), ...[...scoreNames].filter(name => !SCORE_ORDER.includes(name))];
    const parameterGetter = name => round => {
      const value = (round.parameters || {})[name];
      return typeof value === "boolean" ? Number(value) : typeof value === "number" ? value : null;
    };
    const numeric = parameterNames.filter(name => rows.some(row => {
      const detail = JD.detail(row);
      return detail && Object.values(detail.modes).some(run => (run.rounds || []).some(round => typeof (round.parameters || {})[name] === "number" || typeof (round.parameters || {})[name] === "boolean"));
    }));
    const tags = [
      {id: "trouble", group: "scores", name: "trouble", get: round => round.trouble ?? round.utility},
      ...scores.map(name => ({id: `score/${name}`, group: "scores", name, get: round => (round.scores || {})[name]})),
      {id: "cost/cumulativeTokens", group: "cost", name: "cumulativeTokens", get: round => round.tokenEnd},
      {id: "cost/segmentTokens", group: "cost", name: "segmentTokens", get: round => round.tokens},
      {id: "cost/generationSeconds", group: "cost", name: "generationSeconds", get: round => round.generationSeconds},
      {id: "cost/jevSeconds", group: "cost", name: "jevSeconds", get: round => round.jevSeconds},
      {id: "cost/jevInputTokens", group: "cost", name: "jevInputTokens", get: round => round.jevInputTokens},
      ...numeric.map(name => ({id: `parameter/${name}`, group: "parameters", name, get: parameterGetter(name)}))
    ];
    return tags;
  };
  JD.tagTitle = tag => {
    const key = tag.group === "scores" ? "tag." + tag.name : tag.group === "cost" ? "tag." + tag.name : null;
    return key && JD.copy[JD.state.language][key] ? JD.t(key) : tag.name;
  };

  /* ---- tooltip ---- */
  const tip = JD.el("div", null, "tip");
  tip.hidden = true;
  document.body.append(tip);
  JD.tip = {
    show(html, event) {
      tip.innerHTML = html; tip.hidden = false;
      const box = tip.getBoundingClientRect();
      const x = Math.min(event.clientX + 14, window.innerWidth - box.width - 8), y = Math.min(event.clientY + 14, window.innerHeight - box.height - 8);
      tip.style.left = `${Math.max(4, x)}px`; tip.style.top = `${Math.max(4, y)}px`;
    },
    hide() { tip.hidden = true; }
  };
  JD.escape = text => String(text).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})[c]);

  /* ---- cards: title, SVG and CSV download, body ---- */
  function download(name, mime, content) {
    const url = URL.createObjectURL(new Blob([content], {type: mime}));
    const link = document.createElement("a");
    link.href = url; link.download = name;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  JD.card = (title, {wide = false, controls = null, csv = null} = {}) => {
    const node = JD.el("section", null, `card${wide ? " wide" : ""}`);
    const head = JD.el("div", null, "card-head");
    const titleNode = JD.el("h3", title);
    const tools = JD.el("div", null, "card-tools");
    if (controls) tools.append(controls);
    const svgButton = JD.el("button", "SVG", "icon-btn");
    svgButton.type = "button";
    svgButton.onclick = () => {
      const svg = body.querySelector("svg");
      if (!svg) return;
      const clone = svg.cloneNode(true);
      clone.setAttribute("xmlns", NS);
      clone.removeAttribute("style");
      const background = S("rect", {x: 0, y: 0, width: "100%", height: "100%", fill: "#ffffff"});
      clone.insertBefore(background, clone.firstChild);
      download(`jev-${title.replace(/[^\w]+/g, "-")}.svg`, "image/svg+xml;charset=utf-8", '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(clone));
    };
    tools.append(svgButton);
    const csvButton = JD.el("button", "CSV", "icon-btn");
    csvButton.type = "button";
    csvButton.onclick = () => { const rows = node.csvRows ? node.csvRows() : null; if (rows) download(`jev-${title.replace(/[^\w]+/g, "-")}.csv`, "text/csv;charset=utf-8", "﻿" + rows.map(row => row.map(cell => `"${String(cell ?? "").replace(/"/g, '""')}"`).join(",")).join("\r\n")); };
    if (csv !== false) tools.append(csvButton);
    head.append(titleNode, tools);
    const body = JD.el("div", null, "card-body");
    node.append(head, body);
    node.body = body; node.titleNode = titleNode; node.csvRows = null;
    return node;
  };

  /* ---- axes ---- */
  function axes(root, m, W, H, x, y, xTicks, yTicks, {xLabel, yLabel, xFormat = value => JD.fmt(value, 0), yFormat = value => JD.fmt(value, 2)}) {
    for (const tick of yTicks) {
      root.append(S("line", {x1: m.l, x2: W - m.r, y1: y(tick), y2: y(tick), stroke: GRID, "stroke-width": 1}));
      root.append(label(m.l - 7, y(tick) + 4, yFormat(tick), {anchor: "end"}));
    }
    root.append(S("line", {x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, stroke: AXIS}));
    for (const tick of xTicks) {
      root.append(S("line", {x1: x(tick), x2: x(tick), y1: H - m.b, y2: H - m.b + 4, stroke: AXIS}));
      root.append(label(x(tick), H - m.b + 17, xFormat(tick), {anchor: "middle"}));
    }
    if (xLabel) root.append(label((m.l + W - m.r) / 2, H - 6, xLabel, {fill: INK, anchor: "middle", size: 12}));
    if (yLabel) {
      const text = label(14, (m.t + H - m.b) / 2, yLabel, {fill: INK, anchor: "middle", size: 12});
      text.setAttribute("transform", `rotate(-90 14 ${(m.t + H - m.b) / 2})`);
      root.append(text);
    }
  }
  const canvas = (W, H) => {
    const root = S("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "font-family": FONT});
    return root;
  };
  JD.axes = axes; JD.canvas = canvas;
  JD.legend = items => {
    const row = JD.el("div", null, "legend-row");
    for (const item of items) {
      const entry = JD.el("span", item.name);
      entry.style.setProperty("--swatch", item.color);
      if (item.dash) entry.classList.add("dashed");
      row.append(entry);
    }
    return row;
  };

  /* ---- line chart with bands and a TensorBoard-style hover read-out ----
     series: [{name, color, dash, points: [{x, y, n, bands: [[lo, hi], ...]}], faint: [{x, y}]}] */
  JD.lineChart = ({series, xLabel, yLabel, yMin = null, yMax = null, W = 560, H = 300, yFormat, xFormat, xIntegers = true}) => {
    const m = {l: 54, r: 16, t: 14, b: 40};
    const live = series.filter(item => item.points.length);
    const root = canvas(W, H);
    if (!live.length) { root.append(label(W / 2, H / 2, JD.t("noData"), {anchor: "middle", size: 13})); return root; }
    const xs = [...new Set(live.flatMap(item => item.points.map(point => point.x)))].sort((a, b) => a - b);
    const extent = live.flatMap(item => item.points.flatMap(point => [point.y, ...(point.bands || []).flat(), ...[]])).filter(Number.isFinite);
    let low = yMin ?? Math.min(...extent), high = yMax ?? Math.max(...extent);
    if (yMin == null) low = Math.min(low, 0) === 0 && low > 0 ? 0 : low;
    if (high === low) high = low + 1;
    const pad = (high - low) * 0.05;
    if (yMax == null) high += pad;
    if (yMin == null && low < 0) low -= pad;
    const x = JD.linear(xs[0], xs[xs.length - 1] === xs[0] ? xs[0] + 1 : xs[xs.length - 1], m.l, W - m.r), y = JD.linear(low, high, H - m.b, m.t);
    const stride = Math.max(1, Math.ceil(xs.length / 8));
    axes(root, m, W, H, x, y, xIntegers ? xs.filter((_, index) => index % stride === 0) : JD.niceTicks(xs[0], xs[xs.length - 1], 6), JD.niceTicks(low, high, 5), {xLabel, yLabel, yFormat, xFormat});
    for (const item of live) {
      (item.points[0].bands || []).forEach((_, level) => {
        const upper = item.points.map(point => `${x(point.x)},${y(point.bands[level][1])}`);
        const lower = item.points.map(point => `${x(point.x)},${y(point.bands[level][0])}`).reverse();
        root.append(S("polygon", {points: [...upper, ...lower].join(" "), fill: item.color, "fill-opacity": level === 0 ? 0.10 : 0.18, stroke: "none"}));
      });
      if (item.faint && item.faint.length > 1) root.append(S("polyline", {points: item.faint.map(point => `${x(point.x)},${y(point.y)}`).join(" "), fill: "none", stroke: item.color, "stroke-opacity": 0.28, "stroke-width": 1.4, ...(item.dash ? {"stroke-dasharray": item.dash} : {})}));
      root.append(S("polyline", {points: item.points.map(point => `${x(point.x)},${y(point.y)}`).join(" "), fill: "none", stroke: item.color, "stroke-width": 2, "stroke-linejoin": "round", ...(item.dash ? {"stroke-dasharray": item.dash} : {})}));
      if (item.points.length <= 40) for (const point of item.points) root.append(S("circle", {cx: x(point.x), cy: y(point.y), r: 2.4, fill: item.color}));
    }
    const cross = S("line", {y1: m.t, y2: H - m.b, stroke: "#999", "stroke-dasharray": "3 3", visibility: "hidden"});
    root.append(cross);
    const area = S("rect", {x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent"});
    area.addEventListener("mousemove", event => {
      const box = root.getBoundingClientRect();
      const px = (event.clientX - box.left) / box.width * W;
      let best = xs[0];
      for (const value of xs) if (Math.abs(x(value) - px) < Math.abs(x(best) - px)) best = value;
      cross.setAttribute("x1", x(best)); cross.setAttribute("x2", x(best)); cross.setAttribute("visibility", "visible");
      const lines = live.map(item => {
        const point = item.points.find(candidate => candidate.x === best);
        const raw = point && point.raw != null && Math.abs(point.raw - point.y) > 1e-9 ? ` <span>(${JD.fmt(point.raw, 3)})</span>` : "";
        return point ? `<div><i style="background:${item.color}"></i>${JD.escape(item.name)}: <b>${JD.fmt(point.y, 3)}</b>${raw}${point.n != null ? ` <span>n=${point.n}</span>` : ""}</div>` : "";
      }).join("");
      JD.tip.show(`<div class="tip-title">${JD.escape(xLabel || "")} ${JD.fmt(best, 0)}</div>${lines}`, event);
    });
    area.addEventListener("mouseleave", () => { cross.setAttribute("visibility", "hidden"); JD.tip.hide(); });
    root.append(area);
    return root;
  };
  /* Rows for the CSV button of a line chart. */
  JD.seriesCsv = (series, xName) => {
    const xs = [...new Set(series.flatMap(item => item.points.map(point => point.x)))].sort((a, b) => a - b);
    return [[xName, ...series.flatMap(item => [item.name, `${item.name} n`])],
      ...xs.map(value => [value, ...series.flatMap(item => { const point = item.points.find(p => p.x === value); return point ? [point.y, point.n ?? ""] : ["", ""]; })])];
  };
  /* Smoothing and the range band apply to every line chart: curves, distributions, the judge curve and the task drawer.
     smoothPoints() returns the smoothed points (y and every band edge) and, when smoothing is on, the raw line as a faint companion. */
  JD.smoothPoints = points => {
    const weight = JD.state.smoothing;
    if (!weight || !points.length) return {points, faint: null};
    const smoothed = JD.smooth(points.map(point => point.y), weight);
    const levels = (points[0].bands || []).length;
    const edges = Array.from({length: levels}, (_, level) => [0, 1].map(edge => JD.smooth(points.map(point => point.bands[level][edge]), weight)));
    return {
      points: points.map((point, index) => ({...point, raw: point.y, y: smoothed[index], bands: levels ? edges.map(pair => [pair[0][index], pair[1][index]]) : undefined})),
      faint: points.map(point => ({x: point.x, y: point.y}))
    };
  };
  JD.redrawLines = () => {
    for (const id of ["curves", "distributions", "judge"]) if (JD.tabs[id]) JD.tabs[id].dirty = true;
    JD.show(JD.state.tab);
    const drawer = JD.$("drawer");
    if (JD.drawerRedraw && drawer && !drawer.hidden) JD.drawerRedraw();
  };
  /* TensorBoard smoothing: debiased exponential moving average. */
  JD.smooth = (values, weight) => {
    if (!weight) return values.slice();
    let last = 0, count = 0;
    return values.map(value => { last = last * weight + (1 - weight) * value; count++; return last / (1 - Math.pow(weight, count)); });
  };

  /* ---- scatter: one dot per task, clickable.  Log axes line up on whole decades; the largest departures from the diagonal are named. ---- */
  JD.scatter = ({points, xLabel, yLabel, diagonal = false, zeroLine = false, log = false, annotate = 0, W = 560, H = 400}) => {
    const m = {l: 62, r: 22, t: 14, b: 46};
    const root = canvas(W, H);
    const usable = points.filter(point => Number.isFinite(point.x) && Number.isFinite(point.y) && (!log || (point.x > 0 && point.y > 0)));
    if (!usable.length) { root.append(label(W / 2, H / 2, JD.t("noData"), {anchor: "middle", size: 13})); return root; }
    const transform = log ? Math.log10 : value => value;
    const tx = usable.map(point => transform(point.x)), ty = usable.map(point => transform(point.y));
    let x0 = Math.min(...tx), x1 = Math.max(...tx), y0 = Math.min(...ty), y1 = Math.max(...ty);
    if (diagonal) { x0 = y0 = Math.min(x0, y0); x1 = y1 = Math.max(x1, y1); }
    if (log) { x0 = Math.floor(x0); y0 = Math.floor(y0); x1 = Math.ceil(x1); y1 = Math.ceil(y1); if (diagonal) { x0 = y0 = Math.min(x0, y0); x1 = y1 = Math.max(x1, y1); } }
    else {
      if (!zeroLine) { x0 = Math.min(0, x0); y0 = diagonal ? x0 : Math.min(0, y0); }
      else { y0 = Math.min(0, y0); y1 = Math.max(0, y1); x0 = Math.min(0, x0); }
      const xp = (x1 - x0) * 0.04 || 1, yp = (y1 - y0) * 0.04 || 1;
      x1 += xp; y1 += yp; if (zeroLine) y0 -= yp;
      if (diagonal) { x0 = y0 = Math.min(x0, y0); x1 = y1 = Math.max(x1, y1); }
    }
    if (x1 === x0) x1 = x0 + 1;
    if (y1 === y0) y1 = y0 + 1;
    const X = JD.linear(x0, x1, m.l, W - m.r), Y = JD.linear(y0, y1, H - m.b, m.t);
    const compact = value => value >= 1e6 ? `${JD.fmt(value / 1e6, 1)}M` : value >= 1e3 ? `${JD.fmt(value / 1e3, 1)}k` : JD.fmt(value, value < 10 ? 1 : 0);
    const decades = (low, high) => Array.from({length: Math.floor(high) - Math.ceil(low) + 1}, (_, index) => Math.ceil(low) + index);
    const format = value => log ? compact(10 ** value) : JD.fmt(value, 0);
    axes(root, m, W, H, X, Y, log ? decades(x0, x1) : JD.niceTicks(x0, x1, 5), log ? decades(y0, y1) : JD.niceTicks(y0, y1, 5), {xLabel, yLabel, xFormat: format, yFormat: format});
    if (log) {
      for (const decade of decades(x0, x1 - 1)) for (const factor of [2, 3, 4, 5, 6, 7, 8, 9]) {
        const at = decade + Math.log10(factor);
        if (at < x1) root.append(S("line", {x1: X(at), x2: X(at), y1: H - m.b, y2: H - m.b + 2.5, stroke: AXIS}));
      }
      for (const decade of decades(y0, y1 - 1)) for (const factor of [2, 3, 4, 5, 6, 7, 8, 9]) {
        const at = decade + Math.log10(factor);
        if (at < y1) root.append(S("line", {x1: m.l - 2.5, x2: m.l, y1: Y(at), y2: Y(at), stroke: AXIS}));
      }
    }
    if (diagonal) root.append(S("line", {x1: X(x0), y1: Y(x0), x2: X(x1), y2: Y(x1), stroke: "#999", "stroke-dasharray": "5 4"}));
    if (zeroLine && y0 < 0 && y1 > 0) root.append(S("line", {x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0), stroke: "#999", "stroke-dasharray": "5 4"}));
    /* draw the unremarkable dots first so that the coloured ones stay on top */
    const rank = point => point.color === JD.COLOR.adaptive || point.color === JD.COLOR.wrong ? 1 : 0;
    for (const point of usable.slice().sort((a, b) => rank(a) - rank(b))) {
      const dot = S("circle", {cx: X(transform(point.x)), cy: Y(transform(point.y)), r: 4, fill: point.color || JD.COLOR.adaptive, "fill-opacity": 0.8, stroke: "#fff", "stroke-width": 0.8, class: "dot"});
      dot.addEventListener("mousemove", event => JD.tip.show(`<div class="tip-title">${JD.escape(point.row.task)}</div><div>${JD.escape(xLabel)}: <b>${JD.fmt(point.x, 1)}</b></div><div>${JD.escape(yLabel)}: <b>${JD.fmt(point.y, 1)}</b></div>`, event));
      dot.addEventListener("mouseleave", () => JD.tip.hide());
      dot.addEventListener("click", () => JD.openTask(point.row));
      root.append(dot);
    }
    if (annotate && diagonal) {
      const far = usable.slice().sort((a, b) => Math.abs(transform(b.y) - transform(b.x)) - Math.abs(transform(a.y) - transform(a.x))).slice(0, annotate);
      for (const point of far) {
        const px = X(transform(point.x)), py = Y(transform(point.y)), above = point.y > point.x;
        root.append(label(px + (px > W - m.r - 60 ? -7 : 7), py + (above ? -6 : 14), JD.shortId(point.row.task), {size: 10.5, fill: "#444", anchor: px > W - m.r - 60 ? "end" : "start"}));
      }
    }
    return root;
  };

  /* ---- horizontal bars: groups of bars, each group one row ---- */
  JD.bars = ({groups, xLabel, xMax = null, format = value => JD.fmt(value, 0), W = 560, labelWidth = 150, rowHeight = 30}) => {
    const m = {l: labelWidth, r: 60, t: 10, b: 40};
    const H = m.t + m.b + groups.length * rowHeight;
    const root = canvas(W, H);
    const max = xMax ?? Math.max(1e-9, ...groups.flatMap(group => group.bars.map(bar => bar.value || 0)));
    const x = JD.linear(0, max, m.l, W - m.r);
    for (const tick of JD.niceTicks(0, max, 5)) {
      root.append(S("line", {x1: x(tick), x2: x(tick), y1: m.t, y2: H - m.b, stroke: GRID}));
      root.append(label(x(tick), H - m.b + 16, format(tick), {anchor: "middle"}));
    }
    root.append(S("line", {x1: m.l, x2: m.l, y1: m.t, y2: H - m.b, stroke: AXIS}));
    if (xLabel) root.append(label((m.l + W - m.r) / 2, H - 5, xLabel, {fill: INK, anchor: "middle", size: 12}));
    groups.forEach((group, index) => {
      const top = m.t + index * rowHeight, slot = (rowHeight - 6) / group.bars.length;
      root.append(label(m.l - 8, top + rowHeight / 2 + 4, group.label, {anchor: "end", fill: INK, size: 11}));
      group.bars.forEach((bar, position) => {
        if (!Number.isFinite(bar.value) || (bar.value === 0 && !bar.note)) return;
        const width = Math.max(0, x(bar.value) - m.l);
        const rect = S("rect", {x: m.l, y: top + 3 + position * slot, width, height: Math.max(2, slot - 2), fill: bar.color});
        rect.addEventListener("mousemove", event => JD.tip.show(`<div class="tip-title">${JD.escape(group.label)}</div><div>${JD.escape(bar.name || "")}: <b>${format(bar.value)}</b>${bar.note ? ` <span>${JD.escape(bar.note)}</span>` : ""}</div>`, event));
        rect.addEventListener("mouseleave", () => JD.tip.hide());
        root.append(rect, label(m.l + width + 5, top + 3 + position * slot + Math.max(8, slot / 2 + 3), `${format(bar.value)}${bar.note ? ` · ${bar.note}` : ""}`, {size: 10}));
      });
    });
    return root;
  };

  /* ---- histogram with markers ---- */
  JD.histogram = ({values, markers = [], band = null, xLabel, bins = 24, W = 560, H = 300, color = JD.COLOR.adaptive}) => {
    const m = {l: 54, r: 16, t: 24, b: 40};
    const root = canvas(W, H);
    if (!values.length) { root.append(label(W / 2, H / 2, JD.t("noData"), {anchor: "middle", size: 13})); return root; }
    const spread = values.map(Math.abs).sort((a, b) => a - b);
    const power = 10 ** Math.floor(Math.log10(Math.max(1, JD.quantile(spread, 0.95) * 1.3)));
    const bound = Math.max(1, Math.ceil(Math.max(1, JD.quantile(spread, 0.95) * 1.3) / power) * power);
    const low = Math.min(...values) < 0 ? -bound : 0, high = bound;
    const width = (high - low) / bins, counts = new Array(bins).fill(0);
    let tails = 0;
    for (const value of values) {
      if (value < low || value > high) tails++;
      counts[Math.min(bins - 1, Math.max(0, Math.floor((value - low) / width)))]++;
    }
    const top = Math.max(...counts);
    const x = JD.linear(low, high, m.l, W - m.r), y = JD.linear(0, top, H - m.b, m.t);
    axes(root, m, W, H, x, y, JD.niceTicks(low, high, 6), JD.niceTicks(0, top, Math.min(top, 5) || 1), {xLabel, yLabel: JD.t("taskCount"), xFormat: value => JD.signed(value), yFormat: value => JD.fmt(value, 0)});
    if (band && band.every(Number.isFinite)) root.append(S("rect", {x: x(band[0]), y: m.t, width: Math.max(1, x(band[1]) - x(band[0])), height: H - m.t - m.b, fill: color, "fill-opacity": 0.10}));
    counts.forEach((count, index) => {
      if (!count) return;
      const edge = index === 0 || index === bins - 1;
      const bar = S("rect", {x: x(low + index * width) + 0.5, y: y(count), width: Math.max(1, x(low + (index + 1) * width) - x(low + index * width) - 1), height: H - m.b - y(count), fill: color, "fill-opacity": edge && tails ? 0.5 : 0.8});
      bar.addEventListener("mousemove", event => JD.tip.show(`<div>${index === 0 && tails ? "≤ " : ""}${JD.signed(low + index * width)} … ${JD.signed(low + (index + 1) * width)}${index === bins - 1 && tails ? " ≤" : ""}: <b>${count}</b></div>`, event));
      bar.addEventListener("mouseleave", () => JD.tip.hide());
      root.append(bar);
    });
    root.append(S("line", {x1: x(0), x2: x(0), y1: m.t, y2: H - m.b, stroke: INK, "stroke-width": 1}));
    const ordered = markers.slice().sort((p, q) => p.x - q.x);
    ordered.forEach((marker, index) => {
      const right = index === ordered.length - 1 && ordered.length > 1;
      root.append(S("line", {x1: x(marker.x), x2: x(marker.x), y1: m.t - 4, y2: H - m.b, stroke: marker.color, "stroke-width": 1.6, "stroke-dasharray": marker.dash || ""}));
      root.append(label(x(marker.x) + (right ? 5 : -5), m.t - 8, marker.label, {fill: marker.color, anchor: right ? "start" : "end", size: 10.5}));
    });
    return root;
  };

  /* ---- table helper ---- */
  JD.table = (head, rows, {align = []} = {}) => {
    const table = document.createElement("table");
    const thead = document.createElement("thead"), headRow = document.createElement("tr");
    head.forEach((text, index) => { const th = JD.el("th", text); if (align[index] === "r") th.className = "num"; headRow.append(th); });
    thead.append(headRow);
    const tbody = document.createElement("tbody");
    for (const row of rows) {
      const tr = document.createElement("tr");
      row.forEach((cell, index) => {
        const td = cell instanceof Node ? (() => { const holder = document.createElement("td"); holder.append(cell); return holder; })() : JD.el("td", cell);
        if (align[index] === "r") td.classList.add("num");
        tr.append(td);
      });
      tbody.append(tr);
    }
    table.append(thead, tbody);
    const wrap = JD.el("div", null, "table-scroll");
    wrap.append(table);
    return wrap;
  };

  /* ---- tab registry: each tab module registers a renderer ---- */
  JD.register = (id, renderer) => { JD.tabs[id] = {render: renderer, dirty: true}; };
  JD.invalidate = () => { for (const tab of Object.values(JD.tabs)) tab.dirty = true; JD.show(JD.state.tab); };
  JD.show = id => {
    JD.state.tab = id;
    document.querySelectorAll(".tab-btn").forEach(button => button.setAttribute("aria-selected", String(button.dataset.tab === id)));
    document.querySelectorAll(".tab").forEach(panel => { panel.hidden = panel.id !== `tab-${id}`; });
    document.querySelectorAll("[data-for]").forEach(node => { node.hidden = !node.dataset.for.split(" ").includes(id); });
    const bandBox = JD.$("show-band");
    if (bandBox) bandBox.checked = !!JD.state.bands[id];
    const tab = JD.tabs[id];
    if (tab && tab.dirty) { tab.dirty = false; tab.render(); }
  };
  JD.openTask = row => { if (JD.tabs.tasks && JD.tabs.tasks.open) JD.tabs.tasks.open(row); };
})();
