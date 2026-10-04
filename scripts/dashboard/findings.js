"use strict";

/* Key findings: four figures whose titles state the result.
   Each figure is plain SVG with inline presentation attributes, so a downloaded file looks the same
   in a paper, a slide or a browser. Gray = control, blue = adaptive, red = what the reader should look at. */
(() => {
  const GRAY = "#8f8f8f", LIGHT = "#bdbdbd", BLUE = "#1f6fb5", RED = "#c0392b", INK = "#222", MUTED = "#6b6b6b", AXIS = "#b5b5b5", FAINT = "#d4d4d4";
  const FONT = "Inter, 'Segoe UI', 'Microsoft YaHei', sans-serif";
  const W = 640, H = 460, MIN_PAIRS = 5;
  const NS = "http://www.w3.org/2000/svg";

  const TEXT = {
    zh: {
      heading: "关键发现", download: "下载 SVG", figure: "图", pick: "任务", loading: "正在读取逐轮记录…", noPairs: "还没有可比较的配对任务。",
      control: {baseline: "Baseline", fixed: "Fixed"}, adaptive: "Adaptive",
      tokens: "生成 token（含重来中浪费的部分）", delta: "token 变化：Adaptive − 对照",
      moversTitle: (k, n) => `${n} 道题中仅 ${k} 道贡献了 80% 的 token 变动`,
      diffuseTitle: n => `token 变动分散在 ${n} 道题上，没有少数任务主导`,
      fewTitle: n => `目前只配对了 ${n} 道题，样本太少，还看不出分布`,
      netTitle: (net, pct, n) => `${n} 道题合计，相对对照净变化 ${net} token（${pct}）；样本太少，不看分布`,
      budget: mode => `${mode} 耗尽了上下文预算`, biggest: d => `最大变动：${d} token`,
      sharesTitle: (net, pct, k, m, share) => `相对对照净变化 ${net} token（${pct}），前 ${k}/${m} 道题占全部变动的 ${share}%`,
      others: (count, sum) => `其余 ${count} 道题合计 ${sum} token`,
      traceTitle: (id, c, a) => `任务 ${id}：${c} vs ${a}`,
      traceCtrl: (mode, n, end) => `${mode} ${n} 段（${end}）`, traceAd: (n, end) => `Adaptive ${n} 段（${end}）`,
      correct: "答对", wrong: "答错", budgetNoAnswer: "耗尽预算，无答案", stoppedNoAnswer: "自行停止，无答案", other: "未能判分",
      utility: "Jev 综合效用", trouble: "症状总量 trouble（越低越好）", segment: "段", restart: "重来", start: "起点效用",
      noUtility: "对照组没有 Jev 打分，只画 Adaptive。",
      paramsTitle: (zero, total) => zero ? `${total} 个被询问的参数中，${zero} 个从未被调整` : `${total} 个被询问的参数都至少被调整过一次`,
      paramsAxis: "Jev 选择“调整”的比例（%，占被询问次数）", neverUsed: "每轮都被询问，却从未被使用",
      noActivity: "这批结果缺少参数记录，请重新生成仪表盘。"
    },
    en: {
      heading: "Key findings", download: "Download SVG", figure: "Figure", pick: "Task", loading: "Loading round records…", noPairs: "No paired tasks to compare yet.",
      control: {baseline: "Baseline", fixed: "Fixed"}, adaptive: "Adaptive",
      tokens: "generated tokens (including those wasted in restarts)", delta: "token change, adaptive − control",
      moversTitle: (k, n) => `${k} of ${n} tasks carry 80% of the token change`,
      diffuseTitle: n => `Token change is spread over ${n} tasks; no few tasks dominate`,
      fewTitle: n => `Only ${n} tasks paired so far; too few to see a pattern`,
      netTitle: (net, pct, n) => `Net change vs control over ${n} tasks: ${net} tokens (${pct}); too few tasks to judge the spread`,
      budget: mode => `${mode} hit the context budget`, biggest: d => `Largest change: ${d} tokens`,
      sharesTitle: (net, pct, k, m, share) => `Net change vs control: ${net} tokens (${pct}); ${k} of ${m} tasks carry ${share}% of all movement`,
      others: (count, sum) => `The other ${count} tasks sum to ${sum} tokens`,
      traceTitle: (id, c, a) => `Task ${id}: ${c} vs ${a}`,
      traceCtrl: (mode, n, end) => `${mode} ${n} segments (${end})`, traceAd: (n, end) => `adaptive ${n} segments (${end})`,
      correct: "correct", wrong: "wrong", budgetNoAnswer: "out of budget, no answer", stoppedNoAnswer: "stopped without an answer", other: "ungraded",
      utility: "Jev composite utility", trouble: "Trouble: largest symptom severity (lower is better)", segment: "segment", restart: "restart", start: "starting utility",
      noUtility: "The control has no Jev scores, so only adaptive is drawn.",
      paramsTitle: (zero, total) => zero ? `${zero} of ${total} parameters Jev was asked about were never once changed` : `All ${total} parameters Jev was asked about were changed at least once`,
      paramsAxis: "share of questions where Jev chose to change it (%)", neverUsed: "always asked, never used",
      noActivity: "This batch has no parameter records; rebuild the dashboard."
    }
  };
  const L = () => TEXT[state.language];
  /* Older runs have `utility`; runs with symptom scores have `trouble`. */
  const level = round => round.trouble ?? round.utility;
  const signed = (value, digits = 0) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${fmt(Math.abs(value), digits)}`;
  const shortId = task => String(task).replace(/^.*_/, "");

  function S(tag, attributes = {}, text) {
    const node = document.createElementNS(NS, tag);
    for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, String(value));
    if (text != null) node.textContent = text;
    return node;
  }
  function label(x, y, text, {size = 12, fill = INK, anchor = "start", weight = "400", family = FONT} = {}) {
    return S("text", {x, y, "font-size": size, fill, "text-anchor": anchor, "font-weight": weight, "font-family": family}, text);
  }
  const linear = (d0, d1, r0, r1) => value => r0 + (value - d0) / ((d1 - d0) || 1) * (r1 - r0);
  function niceTicks(low, high, count = 5) {
    const span = (high - low) || 1, raw = span / count, power = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map(m => m * power).find(s => s >= raw);
    const ticks = [];
    for (let value = Math.ceil(low / step - 1e-9) * step; value <= high + step * 1e-9; value += step) ticks.push(Math.round(value / step) * step);
    return ticks;
  }
  function cjk(character) { return /[\u3000-\u9fff\uff00-\uffef]/.test(character); }
  function wrap(text, limit) {
    const lines = [];
    let line = "", width = 0, lastSpace = -1;
    for (const character of text) {
      const unit = cjk(character) ? 2 : 1;
      if (width + unit > limit) {
        if (lastSpace > 0) { lines.push(line.slice(0, lastSpace)); line = line.slice(lastSpace + 1); width = [...line].reduce((sum, c) => sum + (cjk(c) ? 2 : 1), 0); }
        else { lines.push(line); line = ""; width = 0; }
        lastSpace = -1;
      }
      if (character === " ") lastSpace = line.length;
      line += character; width += unit;
    }
    if (line) lines.push(line);
    return lines;
  }

  /* White background, left-aligned title (the conclusion), room for a second title line. */
  function frame(title) {
    const root = S("svg", {xmlns: NS, viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": title, "font-family": FONT});
    root.append(S("rect", {x: 0, y: 0, width: W, height: H, fill: "#ffffff"}));
    const lines = wrap(title, 72).slice(0, 2);
    lines.forEach((line, index) => root.append(label(14, 28 + index * 21, line, {size: 16, fill: INK})));
    root.top = lines.length > 1 ? 82 : 62;
    return root;
  }
  function bottomAxis(root, scale, ticks, y, left, right, text, format = value => fmt(value, 0)) {
    root.append(S("line", {x1: left, x2: right, y1: y, y2: y, stroke: AXIS, "stroke-width": 1}));
    for (const tick of ticks) {
      root.append(S("line", {x1: scale(tick), x2: scale(tick), y1: y, y2: y + 4, stroke: AXIS, "stroke-width": 1}));
      root.append(label(scale(tick), y + 17, format(tick), {size: 11, fill: MUTED, anchor: "middle"}));
    }
    if (text) root.append(label((left + right) / 2, y + 38, text, {size: 12, fill: INK, anchor: "middle"}));
  }

  function concentration(pairs) {
    const sizes = pairs.map(pair => Math.abs(pair.d)).sort((a, b) => b - a);
    const total = sizes.reduce((sum, value) => sum + value, 0);
    let running = 0, count = 0;
    if (total > 0) for (const value of sizes) { running += value; count++; if (running >= 0.8 * total) break; }
    const concentrated = pairs.length >= 5 && count > 0 && count <= Math.max(1, Math.ceil(pairs.length * 0.25));
    return {total, count, concentrated};
  }

  function endingText(run) {
    if (run.grade === "correct") return L().correct;
    if (run.grade === "incorrect") return L().wrong;
    if (run.stopReason === "context_budget") return L().budgetNoAnswer;
    if (run.stopReason === "model_stop") return L().stoppedNoAnswer;
    return L().other;
  }

  /* Figure 1: who moves. Dumbbell of the twelve largest changes. */
  function figureMovers(context) {
    const {pairs, control, controlName} = context, text = L();
    const stats = concentration(pairs);
    const title = pairs.length < MIN_PAIRS ? text.fewTitle(pairs.length)
      : stats.concentrated ? text.moversTitle(stats.count, pairs.length) : text.diffuseTitle(pairs.length);
    const root = frame(title);
    const top = pairs.slice().sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(0, 12);
    const hot = new Set(stats.concentrated ? top.slice(0, stats.count).map(pair => pair.row.key) : []);
    top.sort((a, b) => Math.max(b.c, b.a) - Math.max(a.c, a.a));
    const m = {l: 62, r: 30, t: root.top, b: 56};
    const high = Math.max(1, ...top.flatMap(pair => [pair.c, pair.a])) * 1.06;
    const x = linear(0, high, m.l, W - m.r);
    const rowHeight = (H - m.t - m.b) / Math.max(1, top.length);
    const centre = index => m.t + rowHeight * (index + 0.5);
    bottomAxis(root, x, niceTicks(0, high, 6), H - m.b, m.l, W - m.r, text.tokens);
    top.forEach((pair, index) => {
      const y = centre(index), isHot = hot.has(pair.row.key);
      root.append(label(m.l - 10, y + 4, shortId(pair.row.task), {size: 12, fill: INK, anchor: "end"}));
      root.append(S("line", {x1: x(pair.c), x2: x(pair.a), y1: y, y2: y, stroke: isHot ? RED : FAINT, "stroke-width": isHot ? 3 : 2.5, "stroke-linecap": "round"}));
      for (const [value, color, name] of [[pair.c, GRAY, controlName], [pair.a, BLUE, text.adaptive]]) {
        const dot = S("circle", {cx: x(value), cy: y, r: 5.5, fill: color, cursor: "pointer"});
        dot.append(S("title", {}, `${pair.row.task} · ${name}: ${fmt(value, 0)}`));
        dot.addEventListener("click", () => loadDetail(pair.row));
        root.append(dot);
      }
    });
    const lead = top[0];
    if (lead) {
      const bigger = lead.c >= lead.a ? "control" : "adaptive";
      const stop = (bigger === "control" ? lead.row.modes[control] : lead.row.modes.adaptive).stopReason;
      const note = stop === "context_budget" ? text.budget(bigger === "control" ? controlName : text.adaptive) : text.biggest(signed(lead.d));
      const anchorX = x(Math.max(lead.c, lead.a)), y = centre(0);
      root.append(S("line", {x1: anchorX - 6, y1: y + 7, x2: anchorX - 52, y2: y + rowHeight * 0.95, stroke: RED, "stroke-width": 1}));
      root.append(label(anchorX - 56, y + rowHeight * 0.95 + 14, note, {size: 12, fill: RED, anchor: "end"}));
    }
    const key = (index, color, name) => {
      const baseX = W - m.r - 128, baseY = H - m.b - 70 + index * 26;
      root.append(S("circle", {cx: baseX, cy: baseY, r: 6, fill: color}), label(baseX + 14, baseY + 5, name, {size: 13, fill: INK}));
    };
    key(0, GRAY, controlName); key(1, BLUE, text.adaptive);
    return root;
  }

  /* Figure 2: how the token change is shared among tasks. */
  function figureShares(context) {
    const {pairs} = context, text = L();
    const stats = concentration(pairs);
    const net = pairs.reduce((sum, pair) => sum + pair.d, 0);
    const base = pairs.reduce((sum, pair) => sum + pair.c, 0);
    const relative = base ? `${signed(net / base * 100, 1)}%` : "—";
    const shown = Math.min(10, pairs.length);
    const top = pairs.slice().sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(0, shown);
    const covered = top.reduce((sum, pair) => sum + Math.abs(pair.d), 0);
    const share = stats.total ? Math.round(covered / stats.total * 100) : 0;
    const title = pairs.length < MIN_PAIRS ? text.netTitle(signed(net), relative, pairs.length) : text.sharesTitle(signed(net), relative, shown, pairs.length, share);
    const root = frame(title);
    const hot = new Set(stats.concentrated ? top.slice(0, stats.count).map(pair => pair.row.key) : top.slice(0, Math.min(3, top.length)).map(pair => pair.row.key));
    top.sort((a, b) => b.d - a.d);
    const m = {l: 62, r: 26, t: root.top, b: 74};
    const extent = Math.max(1, ...top.map(pair => Math.abs(pair.d)));
    const low = Math.min(0, ...top.map(pair => pair.d)) - extent * 0.16, high = Math.max(0, ...top.map(pair => pair.d)) + extent * 0.16;
    const x = linear(low, high, m.l, W - m.r);
    const rowHeight = (H - m.t - m.b) / Math.max(1, top.length);
    bottomAxis(root, x, niceTicks(low, high, 6), H - m.b, m.l, W - m.r, text.delta, value => signed(value));
    root.append(S("line", {x1: x(0), x2: x(0), y1: m.t - 4, y2: H - m.b, stroke: INK, "stroke-width": 1.2}));
    top.forEach((pair, index) => {
      const y = m.t + rowHeight * index, barHeight = Math.min(26, rowHeight * 0.68), isHot = hot.has(pair.row.key);
      root.append(label(m.l - 10, y + rowHeight / 2 + 4, shortId(pair.row.task), {size: 12, fill: INK, anchor: "end"}));
      const left = Math.min(x(0), x(pair.d)), width = Math.abs(x(pair.d) - x(0));
      const bar = S("rect", {x: left, y: y + (rowHeight - barHeight) / 2, width: Math.max(1, width), height: barHeight, fill: isHot ? RED : LIGHT, cursor: "pointer"});
      bar.append(S("title", {}, `${pair.row.task}: ${signed(pair.d)} tokens`));
      bar.addEventListener("click", () => loadDetail(pair.row));
      root.append(bar);
      const part = stats.total ? Math.abs(pair.d) / stats.total : 0;
      if (isHot && part >= 0.05) {
        const outward = pair.d < 0;
        root.append(label(outward ? left - 5 : left + width + 5, y + rowHeight / 2 + 4, `${Math.round(part * 100)}%`, {size: 12, fill: RED, anchor: outward ? "end" : "start"}));
      }
    });
    const rest = pairs.length - shown;
    if (rest > 0) {
      const others = pairs.slice().sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(shown).reduce((sum, pair) => sum + pair.d, 0);
      root.append(label(m.l, H - 8, text.others(rest, signed(others)), {size: 12, fill: MUTED}));
    }
    return root;
  }

  /* Figure 3: one task, round by round. */
  function figureTrace(context, detail) {
    const {controlName, control} = context, text = L();
    const series = [[control, controlName, GRAY], ["adaptive", text.adaptive, BLUE]]
      .map(([mode, name, color]) => ({mode, name, color, run: detail.modes[mode], rounds: detail.modes[mode].rounds}))
      .filter(item => item.rounds.some(round => Number.isFinite(level(round))));
    const adaptive = detail.modes.adaptive, other = detail.modes[control];
    const title = text.traceTitle(shortId(detail.id), text.traceCtrl(controlName, other.rounds.length, endingText(other)), text.traceAd(adaptive.rounds.length, endingText(adaptive)));
    const root = frame(title);
    const m = {l: 56, r: 26, t: root.top + 22, b: 56};
    const values = series.flatMap(item => item.rounds.map(level)).filter(Number.isFinite);
    const low = Math.max(0, Math.floor((Math.min(...values) - 0.04) * 20) / 20), high = Math.min(1, Math.ceil((Math.max(...values) + 0.04) * 20) / 20);
    const count = Math.max(...series.map(item => item.rounds.length), 2);
    const x = linear(0, count - 1, m.l, W - m.r), y = linear(low, high, H - m.b, m.t);
    for (const tick of niceTicks(low, high, 5)) {
      root.append(S("line", {x1: m.l - 4, x2: m.l, y1: y(tick), y2: y(tick), stroke: AXIS}), label(m.l - 9, y(tick) + 4, fmt(tick, 2), {size: 11, fill: MUTED, anchor: "end"}));
    }
    root.append(S("line", {x1: m.l, x2: m.l, y1: m.t, y2: H - m.b, stroke: AXIS}));
    root.append(label(14, (m.t + H - m.b) / 2, series.some(item => item.rounds.some(round => Number.isFinite(round.trouble))) ? text.trouble : text.utility, {size: 12, fill: INK, anchor: "middle"}));
    root.lastChild.setAttribute("transform", `rotate(-90 14 ${(m.t + H - m.b) / 2})`);
    const stride = Math.max(1, Math.ceil((count - 1) / 6));
    const ticks = Array.from({length: Math.floor((count - 1) / stride) + 1}, (_, index) => 1 + index * stride);
    bottomAxis(root, value => x(value - 1), ticks, H - m.b, m.l, W - m.r, text.segment);
    const first = adaptive.rounds.find(round => Number.isFinite(level(round)));
    if (first) root.append(S("line", {x1: m.l, x2: W - m.r, y1: y(level(first)), y2: y(level(first)), stroke: LIGHT, "stroke-width": 1, "stroke-dasharray": "2 4"}));
    const restarts = [];
    adaptive.rounds.forEach((round, index) => { if (index && round.epoch !== adaptive.rounds[index - 1].epoch) restarts.push(index); });
    restarts.forEach(index => {
      root.append(S("line", {x1: x(index - 0.5), x2: x(index - 0.5), y1: m.t - 6, y2: H - m.b, stroke: RED, "stroke-width": 1, "stroke-dasharray": "4 3"}));
      root.append(label(x(index - 0.5) + 4, m.t + 6, text.restart, {size: 11, fill: RED}));
    });
    for (const item of series) {
      const points = item.rounds.map((round, index) => Number.isFinite(level(round)) ? [x(index), y(level(round)), round] : null).filter(Boolean);
      root.append(S("polyline", {points: points.map(p => `${p[0]},${p[1]}`).join(" "), fill: "none", stroke: item.color, "stroke-width": 2.2, "stroke-linejoin": "round"}));
      for (const [px, py, round] of points) {
        const dot = S("circle", {cx: px, cy: py, r: 3, fill: round.abandoned ? "#ffffff" : item.color, stroke: item.color, "stroke-width": round.abandoned ? 1.5 : 0});
        dot.append(S("title", {}, `${item.name} · ${text.segment} ${round.step + 1}: ${fmt(level(round), 3)}`));
        root.append(dot);
      }
    }
    let cursor = m.l;
    series.forEach(item => {
      const words = `${item.name} · ${item.rounds.length} ${text.segment} · ${endingText(item.run)}`;
      root.append(S("circle", {cx: cursor + 5, cy: m.t - 30, r: 5, fill: item.color}), label(cursor + 15, m.t - 26, words, {size: 12, fill: item.color, weight: "600"}));
      cursor += 15 + [...words].reduce((sum, c) => sum + (cjk(c) ? 12 : 6.6), 0) + 22;
    });
    if (series.length < 2) root.append(label(m.l, H - 8, text.noUtility, {size: 12, fill: MUTED}));
    return root;
  }

  /* Figure 4: which parameters Jev actually uses. */
  function figureParams() {
    const text = L(), activity = (window.JEV_OVERVIEW || {}).parameterActivity;
    if (!activity || !Object.keys(activity).length) return frame(text.noActivity);
    const asked = Object.entries(activity).filter(([, v]) => v[0] > 0).map(([name, [n, changed]]) => ({name, n, changed, rate: changed / n}));
    asked.sort((a, b) => b.rate - a.rate || b.n - a.n);
    const zero = asked.filter(item => item.changed === 0).length;
    const root = frame(text.paramsTitle(zero, asked.length));
    const m = {l: 214, r: 54, t: root.top, b: 56};
    const x = linear(0, 100, m.l, W - m.r);
    const rowHeight = (H - m.t - m.b) / Math.max(1, asked.length);
    bottomAxis(root, x, [0, 20, 40, 60, 80, 100], H - m.b, m.l, W - m.r, text.paramsAxis);
    asked.forEach((item, index) => {
      const y = m.t + rowHeight * index, height = Math.min(14, rowHeight * 0.66);
      root.append(label(m.l - 10, y + rowHeight / 2 + 4, item.name, {size: 11, fill: item.changed ? INK : MUTED, anchor: "end", family: "Consolas, 'Courier New', monospace"}));
      if (item.changed) {
        const bar = S("rect", {x: m.l, y: y + (rowHeight - height) / 2, width: x(item.rate * 100) - m.l, height, fill: BLUE});
        bar.append(S("title", {}, `${item.name}: ${item.changed}/${item.n}`));
        root.append(bar, label(x(item.rate * 100) + 5, y + rowHeight / 2 + 4, `${item.changed}/${item.n}`, {size: 10.5, fill: MUTED}));
      }
    });
    const firstZero = asked.findIndex(item => item.changed === 0);
    if (firstZero >= 0) {
      const yTop = m.t + rowHeight * firstZero + 2, yBottom = m.t + rowHeight * asked.length - 2;
      root.append(S("line", {x1: m.l + 8, x2: m.l + 8, y1: yTop, y2: yBottom, stroke: LIGHT, "stroke-width": 1.5}));
      root.append(label(m.l + 18, (yTop + yBottom) / 2 + 4, text.neverUsed, {size: 12, fill: MUTED}));
    }
    return root;
  }

  function download(svg, name) {
    const xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(svg);
    const url = URL.createObjectURL(new Blob([xml], {type: "image/svg+xml;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = url; link.download = `${name}.svg`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function card(number, name, builder, extra) {
    const node = document.createElement("div");
    node.className = "fig";
    const tools = document.createElement("div");
    tools.className = "fig-tools";
    const tag = document.createElement("span");
    tag.textContent = `${L().figure} ${number}`;
    tools.append(tag);
    if (extra) tools.append(extra);
    const button = document.createElement("button");
    button.type = "button"; button.className = "fig-download"; button.textContent = L().download;
    const holder = document.createElement("div");
    holder.className = "fig-body";
    button.onclick = () => { const svg = holder.querySelector("svg"); if (svg) download(svg, `jev-${name}`); };
    tools.append(button);
    node.append(tools, holder);
    builder(holder);
    return node;
  }

  let traceKey = null, traceTicket = 0;
  function drawTrace(holder, context, rows) {
    const choices = rows.slice().sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(0, 12);
    if (!choices.length) { holder.replaceChildren(frame(L().noPairs)); return; }
    if (!choices.some(pair => pair.row.key === traceKey)) traceKey = choices[0].row.key;
    const target = choices.find(pair => pair.row.key === traceKey).row;
    const ticket = ++traceTicket;
    const show = () => {
      if (ticket !== traceTicket) return;
      holder.replaceChildren(figureTrace(context, window.JEV_TASKS[target.key]));
    };
    if (window.JEV_TASKS[target.key]) { show(); return; }
    holder.replaceChildren(frame(L().loading));
    const script = document.createElement("script");
    script.src = `data/tasks/${target.key}.js`;
    script.onload = show;
    script.onerror = () => holder.replaceChildren(frame(L().loading));
    document.body.append(script);
  }

  window.renderFindings = function renderFindings(rows) {
    const host = document.getElementById("findings");
    if (!host) return;
    const control = state.control, text = L();
    const controlName = text.control[control] || control;
    const pairs = rows.map(row => ({row, c: row.modes[control].generatedTokens, a: row.modes.adaptive.generatedTokens}))
      .filter(pair => Number.isFinite(pair.c) && Number.isFinite(pair.a)).map(pair => ({...pair, d: pair.a - pair.c}));
    if (!pairs.length) { host.replaceChildren(Object.assign(document.createElement("p"), {className: "fig-empty", textContent: text.noPairs})); return; }
    const context = {pairs, control, controlName};
    const select = document.createElement("select");
    select.className = "fig-select";
    select.setAttribute("aria-label", text.pick);
    pairs.slice().sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(0, 12).forEach(pair => {
      const option = document.createElement("option");
      option.value = pair.row.key; option.textContent = `${shortId(pair.row.task)} (Δ ${signed(pair.d)})`;
      select.append(option);
    });
    if (traceKey && [...select.options].some(option => option.value === traceKey)) select.value = traceKey;
    const trace = card(3, "trace", holder => drawTrace(holder, context, pairs), select);
    select.onchange = () => { traceKey = select.value; drawTrace(trace.querySelector(".fig-body"), context, pairs); };
    host.replaceChildren(
      card(1, "movers", holder => holder.append(figureMovers(context))),
      card(2, "shares", holder => holder.append(figureShares(context))),
      trace,
      card(4, "parameters", holder => holder.append(figureParams()))
    );
  };

  window.renderFindings(selectedTasks());
})();
