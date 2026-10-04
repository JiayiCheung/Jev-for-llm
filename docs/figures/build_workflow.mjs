import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const directory = dirname(fileURLToPath(import.meta.url));
const words = {
  zh: {
    title: '单次 run：Jev 引导的分段推理', subtitle: '一道题、一个种子的完整循环 · fixed 只评分，是对照；adaptive 才干预（调参、重来）',
    config: ['加载并校验三份配置', 'config.json · parameters.json', 'jev_questions.json → 六项评分规则（带 kind）'],
    initial: ['构造初始采样映射', 'initial_parameters：name → initial', 'request_parameters：name → api_name'],
    setup: ['准备 Qwen 与本轮输出', 'PythonBackend 持有一个 vLLM 模型', '聊天模板编码题目；建立 result.json / answer.txt'],
    preflight: ['本轮还能发起生成吗？', '上下文窗口里还有空位', '请求通过 vLLM 的参数校验'],
    request: ['构造 generation_request', 'prompt = 提示词 token + 已生成 token ID', 'max_tokens = 段长与剩余空间的较小者；seed + step'],
    requestLog: ['生成前写入 result.json', 'rounds[].applied_parameters', 'rounds[].generation_request'],
    generate: ['vLLM 生成一个片段', '把原生字段交给 SamplingParams', 'LLM.generate 返回 token ID 与结束原因'],
    decode: ['校验、拼接并解码', '把新 token ID 接到累计序列', '新片段加入 segments 列表（每段只出现一次）'],
    answerLog: ['保存当前答案快照', 'rounds[].answer_snapshot', 'answer.txt 追加本轮累计答案'],
    score: ['Jev 请求 ①：六项 Score', 'score_request：task / segments / about', '五个症状 + on_track 预测'],
    scoreLog: ['记录评分请求与返回', 'evaluation_request / response', '请求耗时与 Jev 调用次数'],
    parse: ['计算 severity、p_severe、trouble', 'severity = 期望档位 ÷ 4；p_severe = 最高两档概率', 'trouble = 加权后最大的严重度；worst 指明是哪项'],
    stop: ['本轮是否应当结束？', '模型自己停止，或上下文已满', '没有其他结束条件'],
    finish: ['结束并保存最终状态', 'stop_reason 与各轮记录留在 result.json', '已生成文字仍在 answer.txt'],
    modeGate: ['是 adaptive 模式吗？', 'fixed 是对照：Jev 只评分', 'baseline 根本不调用 Jev'],
    hold: ['fixed 对照：全部保持', '不调参数，也不重来', '下一段沿用相同参数'],
    restartGate: ['到了重来检查点吗？', '第 first_check_round 轮起，之后每 20 轮', '已重来次数小于 max_restarts'],
    ckCall: ['Jev 请求 ④：选重来位置', 'continue，或回到更早的 back_k', '看得到每个检查点的 on_track 轨迹'],
    ckGate: ['Jev 选了某个检查点吗？', 'continue：本轮记为新的检查点', 'back_k：进入重来分支'],
    restart: ['从检查点重来', '把 token 和参数都退回检查点', '试探若干段 · Jev 请求 ⑤ 比较 · 至多 3 次'],
    signals: ['为 Jev 整理信号', 'gauges_now · at_start · recent_3 · persistence', 'my_recent_changes · parameter_ages · reading_guide'],
    directionCall: ['Jev 请求 ②：逐参数选动作', '按类型给选项；休眠或被封顶的不出现', '附任务、各片段、信号与全部当前值'],
    parseDirection: ['校验方向 Choice 返回', 'parse_choices 核对选项与概率分布', 'keep 不产生具体值问题'],
    exactGate: ['需要具体值吗？', '预设或单一目标可直接确定', '多个候选才生成 value_request'],
    valueCall: ['Jev 请求 ③：选择具体值', '从程序给出的合法值中选一项', 'chosen_values 映射回真实参数值'],
    commit: ['提交本轮决策', 'Controller.commit 记录真正发生的改动', '同向封顶与休眠的计数在此更新'],
    next: ['准备下一轮生成', '复制 decision.parameters；标记 will_execute', '新值在下一轮 generation_request 才实际生效'],
    zoneSetup: '准备', zoneSegment: '一段推理（所有模式）', zoneJev: 'Jev 干预（仅 adaptive）',
    no: '否', yes: '是', fixed: 'fixed', adaptive: 'adaptive', due: '到点', notDue: '未到', cont: 'continue', back: 'back_k',
  },
  en: {
    title: 'One run: Jev-guided segmented inference', subtitle: 'One task and seed · fixed only scores (the control); adaptive also intervenes (parameters, restart)',
    config: ['Load and validate three inputs', 'config.json · parameters.json', 'jev_questions.json → six rubrics with kind'],
    initial: ['Build initial sampling map', 'initial_parameters: name → initial', 'request_parameters: name → api_name'],
    setup: ['Prepare Qwen and run records', 'PythonBackend holds one vLLM model', 'Encode task; create result.json / answer.txt'],
    preflight: ['May this round generate?', 'Room left in the context window', 'Request passes vLLM parameter validation'],
    request: ['Build generation_request', 'prompt = prompt tokens + prior output token IDs', 'max_tokens = chunk or remaining room; seed + step'],
    requestLog: ['Save before generation', 'rounds[].applied_parameters', 'rounds[].generation_request'],
    generate: ['Generate one vLLM segment', 'Pass native fields to SamplingParams', 'LLM.generate returns token IDs and finish reason'],
    decode: ['Validate, append, decode', 'Append new IDs to the accumulated sequence', 'Add the new text to the segments list (each once)'],
    answerLog: ['Save answer snapshot', 'rounds[].answer_snapshot', 'answer.txt: cumulative answer by round'],
    score: ['Jev call ①: six Scores', 'score_request: task / segments / about', 'Five symptoms and the on_track forecast'],
    scoreLog: ['Save Score request and result', 'evaluation_request / response', 'Elapsed time and Jev call count'],
    parse: ['Compute severity, p_severe, trouble', 'severity = expected level ÷ 4; p_severe = top two levels', 'trouble = largest weighted severity; worst names it'],
    stop: ['Should this run stop now?', 'The model stopped, or the context is full', 'Nothing else ends a run'],
    finish: ['Finish and save final status', 'stop_reason and rounds remain in result.json', 'Generated text remains in answer.txt'],
    modeGate: ['Is this adaptive mode?', 'fixed is the control: Jev only scores', 'baseline never calls Jev'],
    hold: ['Fixed control: keep everything', 'No parameter change, no restart', 'Same parameters in the next segment'],
    restartGate: ['Is a restart check due?', 'From first_check_round, then every 20 rounds', 'Fewer than max_restarts used so far'],
    ckCall: ['Jev call ④: pick a restart point', 'continue, or back_k to an earlier mark', 'Sees the on_track trace of every mark'],
    ckGate: ['Did Jev choose a mark?', 'continue: this round becomes a new mark', 'back_k: take the restart branch'],
    restart: ['Restart from the mark', 'Rewind tokens and parameters to the mark', 'Probe rounds · Jev call ⑤ compares · up to 3 tries'],
    signals: ['Build the signals for Jev', 'gauges_now · at_start · recent_3 · persistence', 'my_recent_changes · parameter_ages · reading_guide'],
    directionCall: ['Jev call ②: one Choice per parameter', 'Options by type; dormant or capped ones are left out', 'Sees task, segments, signals and all current values'],
    parseDirection: ['Validate direction Choices', 'parse_choices checks options and probabilities', 'keep needs no exact-value question'],
    exactGate: ['Is an exact value needed?', 'Presets and single targets resolve directly', 'Several candidates need a value_request'],
    valueCall: ['Jev call ③: choose exact values', 'Select among program-generated legal options', 'chosen_values maps back to real parameter values'],
    commit: ['Commit this round’s decision', 'Controller.commit records the actual changes', 'Same-direction cap and dormancy are updated'],
    next: ['Prepare the next round', 'Copy decision.parameters; set will_execute', 'New values reach the next generation_request'],
    zoneSetup: 'Setup', zoneSegment: 'One segment (all modes)', zoneJev: 'Jev intervenes (adaptive only)',
    no: 'No', yes: 'Yes', fixed: 'fixed', adaptive: 'adaptive', due: 'due', notDue: 'not due', cont: 'continue', back: 'back_k',
  },
};

const escapeXml = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const place = {
  config:[800,298,680,114], initial:[800,447,680,114],
  setup:[800,596,680,114], preflight:[800,745,680,114], request:[800,894,680,135],
  requestLog:[80,894,420,135], generate:[800,1064,680,114], decode:[800,1213,680,114],
  answerLog:[80,1213,420,114], score:[800,1362,680,135], scoreLog:[80,1362,420,135],
  parse:[800,1532,680,135], stop:[800,1702,680,114], finish:[80,1702,420,114],
  modeGate:[800,1851,680,114], hold:[80,1851,420,135],
  restartGate:[800,2000,680,114], ckCall:[1830,2000,540,114],
  signals:[800,2149,680,135], ckGate:[1830,2149,540,135],
  directionCall:[800,2319,680,135], restart:[1830,2319,540,135],
  parseDirection:[800,2489,680,114], exactGate:[800,2638,680,114],
  valueCall:[800,2787,680,114], commit:[800,2936,680,114], next:[800,3085,680,114],
};
const kind = {
  config:'normal', initial:'normal', setup:'normal', preflight:'decision',
  request:'emphasis', requestLog:'record', generate:'emphasis', decode:'normal',
  answerLog:'record', score:'jev', scoreLog:'record', parse:'normal',
  stop:'decision', finish:'finish', modeGate:'decision', hold:'normal',
  restartGate:'decision', ckCall:'jev', ckGate:'decision', restart:'emphasis',
  signals:'normal', directionCall:'jev', parseDirection:'normal', exactGate:'decision',
  valueCall:'jev', commit:'emphasis', next:'emphasis',
};
const edge = (d, cls='') => `<path d="${d}" class="edge ${cls}" marker-end="url(#arrowhead)"/>`;
const label = (x,y,t) => `<text x="${x}" y="${y}" class="edge-label">${escapeXml(t)}</text>`;

function node(key, lines) {
  const [x,y,w,h] = place[key];
  const first = y + (lines.length === 3 ? 35 : 45);
  return `<g><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="2" class="node ${kind[key]}"/>
    <text x="${x+w/2}" y="${first}" text-anchor="middle" class="node-title">${escapeXml(lines[0])}</text>
    ${lines.slice(1).map((line,i)=>`<text x="${x+w/2}" y="${first+35+i*28}" text-anchor="middle" class="node-detail">${escapeXml(line)}</text>`).join('')}
  </g>`;
}

function diagram(lang) {
  const t = words[lang];
  const keys = Object.keys(place);
  const paths = [
    edge('M1140 412 V447'),edge('M1140 561 V596'),
    edge('M1140 710 V745'),edge('M1140 859 V894'),edge('M1140 1029 V1064'),
    edge('M800 802 H30 V1759 H80','branch'),
    edge('M800 961 H500','record'),edge('M1140 1178 V1213'),
    edge('M800 1270 H500','record'),edge('M1140 1327 V1362'),
    edge('M800 1429 H500','record'),edge('M1140 1497 V1532'),
    edge('M1140 1667 V1702'),edge('M800 1759 H500','branch'),
    edge('M1140 1816 V1851'),edge('M800 1908 H500','branch'),
    edge('M1140 1965 V2000'),edge('M1480 2057 H1830','branch'),
    edge('M1140 2114 V2149'),edge('M2100 2114 V2149'),
    edge('M1830 2216 H1480','branch'),edge('M2100 2284 V2319','branch'),
    edge('M1140 2284 V2319'),edge('M1140 2454 V2489'),
    edge('M1140 2603 V2638'),edge('M1140 2752 V2787'),
    edge('M1140 2901 V2936'),edge('M1140 3050 V3085'),
    edge('M1480 2695 H1600 V2993 H1480','bypass'),
    edge('M290 1986 V3142 H800','branch'),
    edge('M2370 2386 H2470','loop'),
    edge('M1140 3199 V3223 H2470 V802 H1480','loop'),
  ];
  const tags = [
    label(540,1746,t.yes),label(1158,1840,t.no),
    label(540,1895,t.fixed),label(1158,1988,t.adaptive),
    label(1510,2044,t.due),label(1158,2138,t.notDue),
    label(1600,2204,t.cont),label(2120,2308,t.back),
    label(1510,2684,t.no),label(1158,2776,t.yes),
  ];
  const zones = [
    `<text x="2440" y="194" text-anchor="end" class="zone">${escapeXml(t.zoneSetup)}</text>`,
    `<text x="2440" y="791" text-anchor="end" class="zone">${escapeXml(t.zoneSegment)}</text>`,
    `<text x="2440" y="1761" text-anchor="end" class="zone">${escapeXml(t.zoneJev)}</text>`,
  ];
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2520 3130" role="img" aria-labelledby="title desc">
  <title id="title">${escapeXml(t.title)}</title>
  <desc id="desc">${escapeXml(t.subtitle)}</desc>
  <defs><marker id="arrowhead" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto"><path d="M1 1 L10 6 L1 11" fill="none" stroke="#626262" stroke-width="1.6"/></marker></defs>
  <style>
    .node{fill:#f0f0ec;stroke:#737373;stroke-width:1.8}
    .node.emphasis{fill:#e4eedc;stroke:#718369}
    .node.jev{fill:#fff0ce;stroke:#8e805f}
    .node.decision{fill:#fafafa;stroke:#777;stroke-dasharray:6 5}
    .node.record{fill:#e9e8f3;stroke:#77788a}.node.finish{fill:#ededed;stroke:#777}
    .node-title{fill:#2d2d2d;font:700 26px Arial,'Microsoft YaHei',sans-serif}
    .node-detail{fill:#4b4b4b;font:20px Arial,'Microsoft YaHei',sans-serif}
    .edge{fill:none;stroke:#626262;stroke-width:2.2;stroke-linejoin:round;stroke-linecap:round}
    .edge.record,.edge.branch,.edge.bypass,.edge.loop{stroke:#626262}
    .zone{fill:#7a7a7a;font:700 22px Arial,'Microsoft YaHei',sans-serif}
    .edge-label{fill:#454545;font:700 19px Arial,'Microsoft YaHei',sans-serif}
  </style>
  <rect width="2520" height="3130" fill="#fff"/>
  <rect x="12" y="12" width="2496" height="3106" fill="none" stroke="#8a8a8a" stroke-width="1.8" stroke-dasharray="4 6"/>
  <rect x="44" y="160" width="2432" height="582" fill="#f5f5f5"/>
  <rect x="44" y="757" width="2432" height="955" fill="#f7f7f7"/>
  <rect x="44" y="1727" width="2432" height="1388" fill="#f5f5f5"/>
  <text x="65" y="75" fill="#292929" font-family="Arial,'Microsoft YaHei',sans-serif" font-size="47" font-weight="700">${escapeXml(t.title)}</text>
  <text x="67" y="120" fill="#555" font-family="Arial,'Microsoft YaHei',sans-serif" font-size="23">${escapeXml(t.subtitle)}</text>
  <path d="M65 138 H2455" stroke="#a0a0a0" stroke-width="1.5"/>
  <g transform="translate(0,-120)">
    ${paths.join('\n    ')}
    ${keys.map(key=>node(key,t[key])).join('\n    ')}
    ${tags.join('\n    ')}
  </g>
  ${zones.join('\n  ')}
</svg>
`;
}

for (const lang of Object.keys(words)) {
  writeFileSync(join(directory, `workflow_${lang}.svg`), diagram(lang), 'utf8');
}
