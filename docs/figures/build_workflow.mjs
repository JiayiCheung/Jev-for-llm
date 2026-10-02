import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const directory = dirname(fileURLToPath(import.meta.url));
const words = {
  zh: {
    title: '单次 run：Jev 引导的分段推理', subtitle: '从参数初始化到下一段生效 · 一道题、一个种子的完整循环',
    start: ['运行 run.py run', 'cli.main 读取任务与种子', '每轮可依据 Jev 反馈调整参数'],
    config: ['加载并校验三份配置', 'config.json · parameters.json', 'jev_questions.json → control 与评分规则'],
    initial: ['构造初始采样映射', 'initial_parameters：name → initial', 'request_parameters：name → api_name'],
    setup: ['准备 Qwen 与本轮输出', 'PythonBackend 持有一个 vLLM 模型', '聊天模板编码题目；建立 result.json / answer.txt'],
    preflight: ['本轮还能发起生成吗？', '检查轮次、剩余 token、上下文空间', '以及 Jev 请求次数上限'],
    request: ['构造 generation_request', 'prompt = 提示词 token + 已生成 token ID', 'max_tokens = 三种剩余额度最小值；seed + step'],
    requestLog: ['生成前写入 result.json', 'rounds[].applied_parameters', 'rounds[].generation_request'],
    generate: ['vLLM 生成一个片段', '把原生字段交给 SamplingParams', 'LLM.generate 返回 token ID 与结束原因'],
    decode: ['校验、拼接并解码', '把新 token ID 接到累计序列', '得到全文 generated 与本段 recent'],
    answerLog: ['保存当前答案快照', 'rounds[].answer_snapshot', 'answer.txt 追加本轮累计答案'],
    score: ['Jev 请求 ①：四项 Score', 'score_request：task / generated / recent / step', '正确性 · 相关性 · 重复性 · 完整性'],
    scoreLog: ['记录评分请求与返回', 'evaluation_request / response', '请求耗时与 Jev 调用次数'],
    parse: ['解析评分并计算效用', '验证答案与概率；0–4 映射到 0–1', '重复性取反后按权重汇总'],
    stop: ['本轮是否应当结束？', '模型停止 / 可选评分停止', 'token、上下文、轮次或 Jev 预算耗尽'],
    finish: ['结束并保存最终状态', 'stop_reason 与各轮记录留在 result.json', '已生成文字仍在 answer.txt'],
    rollback: ['上轮调整导致效用下降？', '比较本轮效用与改动前效用', '下降超过 rollback.score_drop 才回退'],
    restore: ['恢复改动前的参数', '文字不会回退', '下一段才使用恢复后的值'],
    cooldown: ['目前仍在冷却期？', '根据 last_change 与 cooldown_rounds 判断', '冷却时跳过新的 Jev Choice'],
    hold: ['保持当前参数', '本轮不产生新改动', '下一段沿用当前值'],
    directions: ['按类型生成方向候选', '数值 / 可空数值 / 布尔 / 枚举', '其他类型只给可行项；无候选则保持'],
    directionCall: ['Jev 请求 ②：选择动作', 'direction_request 合并各参数 Choice', '每题附当前值、说明与本轮 Score'],
    parseDirection: ['校验方向 Choice 返回', 'parse_choices 核对选项与概率分布', 'keep 不产生具体值问题'],
    candidates: ['构造合法的具体值', '数值按窗口与步长给 1–3 步', '其他类型使用已审核候选或直接切换'],
    exactGate: ['是否存在多个具体候选？', '单一目标值可直接确定', '多个候选才生成 value_request'],
    valueCall: ['Jev 请求 ③：选择具体值', '从程序给出的合法值中选一项', 'chosen_values 映射回真实参数值'],
    commit: ['提交本轮决策', 'Controller.commit 合并真正发生的改动', '记录 pending，供下一轮检验或回退'],
    next: ['准备下一轮生成', '复制 decision.parameters；标记 will_execute', '新值在下一轮 generation_request 才实际生效'],
    no: '否', yes: '是', rollbackYes: '需要回退', cooldownYes: '冷却中',
    ready: '可调整', one: '单一目标 / 无需再问', many: '多个候选',
  },
  en: {
    title: 'One run: Jev-guided segmented inference', subtitle: 'From initial parameters to the next segment · one task and seed',
    start: ['Run run.py run', 'cli.main loads tasks and seeds', 'Jev feedback may update next-round settings'],
    config: ['Load and validate three inputs', 'config.json · parameters.json', 'jev_questions.json → controls and Score rubrics'],
    initial: ['Build initial sampling map', 'initial_parameters: name → initial', 'request_parameters: name → api_name'],
    setup: ['Prepare Qwen and run records', 'PythonBackend holds one vLLM model', 'Encode task; create result.json / answer.txt'],
    preflight: ['May this round generate?', 'Check rounds, remaining tokens, context', 'and Jev request budget'],
    request: ['Build generation_request', 'prompt = prompt tokens + prior output token IDs', 'max_tokens = smallest remaining limit; seed + step'],
    requestLog: ['Save before generation', 'rounds[].applied_parameters', 'rounds[].generation_request'],
    generate: ['Generate one vLLM segment', 'Pass native fields to SamplingParams', 'LLM.generate returns token IDs and finish reason'],
    decode: ['Validate, append, decode', 'Append new IDs to accumulated token sequence', 'Produce full generated text and recent segment'],
    answerLog: ['Save answer snapshot', 'rounds[].answer_snapshot', 'answer.txt: cumulative answer by round'],
    score: ['Jev call ①: four Scores', 'score_request: task / generated / recent / step', 'Correctness · relevance · repetition · completeness'],
    scoreLog: ['Save Score request and result', 'evaluation_request / response', 'Elapsed time and Jev call count'],
    parse: ['Parse Scores and compute utility', 'Validate answers/probabilities; map 0–4 to 0–1', 'Invert repetition; calculate weighted utility'],
    stop: ['Should this run stop now?', 'Model stop / optional Score stop', 'Token, context, round, or Jev budget reached'],
    finish: ['Finish and save final status', 'stop_reason and rounds remain in result.json', 'Generated text remains in answer.txt'],
    rollback: ['Did the last change lower utility?', 'Compare current utility with pre-change utility', 'Revert only beyond rollback.score_drop'],
    restore: ['Restore prior parameters', 'Generated text remains unchanged', 'Restored values apply next segment'],
    cooldown: ['Still in the cooldown period?', 'Check last_change and cooldown_rounds', 'Skip new Jev Choices while cooling down'],
    hold: ['Keep current parameters', 'No new change this round', 'Reuse current values next segment'],
    directions: ['Build type-specific actions', 'Numeric / nullable numeric / boolean / enum', 'Other types; no options means keep'],
    directionCall: ['Jev call ②: choose actions', 'direction_request groups parameter Choices', 'Each includes current value, meaning, and Scores'],
    parseDirection: ['Validate direction Choices', 'parse_choices checks options and probabilities', 'keep needs no exact-value question'],
    candidates: ['Generate legal exact values', 'Numeric: one to three bounded steps', 'Other types: reviewed candidates or direct switch'],
    exactGate: ['More than one exact candidate?', 'Single-target actions resolve directly', 'Multiple values require a value_request'],
    valueCall: ['Jev call ③: choose exact values', 'Select among program-generated legal options', 'chosen_values maps back to real parameter values'],
    commit: ['Commit this round’s decision', 'Controller.commit merges actual changes', 'Save pending state for next-round feedback'],
    next: ['Prepare the next round', 'Copy decision.parameters; set will_execute', 'New values reach the next generation_request'],
    no: 'No', yes: 'Yes', rollbackYes: 'rollback', cooldownYes: 'cooldown',
    ready: 'ready to adjust', one: 'one target / no extra call', many: 'multiple values',
  },
};

const escapeXml = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const place = {
  start:[560,155,680,108], config:[560,298,680,114], initial:[560,447,680,114],
  setup:[560,596,680,114], preflight:[560,745,680,114], request:[560,894,680,135],
  requestLog:[65,894,420,135], generate:[560,1064,680,114], decode:[560,1213,680,114],
  answerLog:[65,1213,420,114], score:[560,1362,680,135], scoreLog:[65,1362,420,135],
  parse:[560,1532,680,135], stop:[560,1702,680,114], finish:[65,1702,420,114],
  rollback:[560,1851,680,114], restore:[65,1851,420,114],
  cooldown:[560,2000,680,114], hold:[65,2000,420,114],
  directions:[1305,2000,420,135], directionCall:[1305,2170,420,114],
  parseDirection:[1305,2319,420,114], candidates:[1305,2468,420,135],
  exactGate:[1305,2638,420,114], valueCall:[1305,2787,420,114],
  commit:[1305,2936,420,114], next:[560,3085,680,114],
};
const kind = {
  start:'start', config:'normal', initial:'normal', setup:'normal', preflight:'decision',
  request:'emphasis', requestLog:'record', generate:'emphasis', decode:'normal',
  answerLog:'record', score:'jev', scoreLog:'record', parse:'normal',
  stop:'decision', finish:'finish', rollback:'decision', restore:'normal',
  cooldown:'decision', hold:'normal', directions:'emphasis', directionCall:'jev',
  parseDirection:'normal', candidates:'normal', exactGate:'decision',
  valueCall:'jev', commit:'emphasis', next:'emphasis',
};
const edge = (d, cls='') => `<path d="${d}" class="edge ${cls}" marker-end="url(#arrowhead)"/>`;
const label = (x,y,t) => `<text x="${x}" y="${y}" class="edge-label">${escapeXml(t)}</text>`;

function node(key, lines) {
  const [x,y,w,h] = place[key];
  const first = y + (lines.length === 3 ? 35 : 45);
  return `<g><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="20" class="node ${kind[key]}"/>
    <text x="${x+w/2}" y="${first}" text-anchor="middle" class="node-title">${escapeXml(lines[0])}</text>
    ${lines.slice(1).map((line,i)=>`<text x="${x+w/2}" y="${first+35+i*28}" text-anchor="middle" class="node-detail">${escapeXml(line)}</text>`).join('')}
  </g>`;
}

function diagram(lang) {
  const t = words[lang];
  const keys = Object.keys(place);
  const paths = [
    edge('M900 263 V298'),edge('M900 412 V447'),edge('M900 561 V596'),
    edge('M900 710 V745'),edge('M900 859 V894'),edge('M900 1029 V1064'),
    edge('M560 802 H30 V1759 H65','branch'),
    edge('M560 961 H485','record'),edge('M900 1178 V1213'),
    edge('M560 1270 H485','record'),edge('M900 1327 V1362'),
    edge('M560 1429 H485','record'),edge('M900 1497 V1532'),
    edge('M900 1667 V1702'),edge('M560 1759 H485','branch'),
    edge('M900 1816 V1851'),edge('M560 1908 H485','branch'),
    edge('M900 1965 V2000'),edge('M560 2057 H485','branch'),
    edge('M1240 2057 H1305','branch'),
    edge('M1515 2135 V2170'),edge('M1515 2284 V2319'),
    edge('M1515 2433 V2468'),edge('M1515 2603 V2638'),
    edge('M1515 2752 V2787'),edge('M1515 2901 V2936'),
    edge('M1305 2695 H1268 V2993 H1305','bypass'),
    edge('M1305 2068 H1278 V3138 H1240','bypass'),
    edge('M1725 2993 H1770 V3142 H1240','branch'),
    edge('M275 1965 V3060 H530 V3142 H560','branch'),
    edge('M350 2114 V3030 H500 V3110 H560','branch'),
    edge('M900 3199 V3223 H1780 V802 H1240','loop'),
  ];
  const tags = [
    label(505,1746,t.yes),label(918,1840,t.no),
    label(505,1895,t.rollbackYes),label(918,1988,t.no),
    label(505,2045,t.cooldownYes),label(1248,2044,t.ready),
    label(1535,2768,t.many),label(1215,2773,t.one),
  ];
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1800 3250" role="img" aria-labelledby="title desc">
  <title id="title">${escapeXml(t.title)}</title>
  <desc id="desc">${escapeXml(t.subtitle)}</desc>
  <defs><marker id="arrowhead" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto"><path d="M1 1 L10 6 L1 11" fill="none" stroke="#8ab6d4" stroke-width="1.8"/></marker></defs>
  <style>
    .node{fill:#12273e;stroke:#386381;stroke-width:2}
    .node.start,.node.emphasis{fill:#10395b;stroke:#448ec2}
    .node.jev{fill:#10374d;stroke:#38abc0}
    .node.decision{fill:#0b2033;stroke:#6ba3c7;stroke-dasharray:7 6}
    .node.record{fill:#142434;stroke:#526d80}.node.finish{fill:#243142;stroke:#75899a}
    .node-title{fill:#e6f4ff;font:700 26px Arial,'Microsoft YaHei',sans-serif}
    .node-detail{fill:#b5cee0;font:20px Arial,'Microsoft YaHei',sans-serif}
    .edge{fill:none;stroke:#8ab6d4;stroke-width:2.6;stroke-linejoin:round;stroke-linecap:round}
    .edge.record{stroke:#708c9e}.edge.branch{stroke:#83a7c2}.edge.bypass{stroke:#55b6ca}.edge.loop{stroke:#4fc0dd;stroke-width:3}
    .edge-label{fill:#9ddafa;font:700 19px Arial,'Microsoft YaHei',sans-serif}
  </style>
  <rect width="1800" height="3250" rx="28" fill="#081522"/>
  <text x="65" y="75" fill="#ecf7ff" font-family="Arial,'Microsoft YaHei',sans-serif" font-size="47" font-weight="700">${escapeXml(t.title)}</text>
  <text x="67" y="120" fill="#aac8dc" font-family="Arial,'Microsoft YaHei',sans-serif" font-size="23">${escapeXml(t.subtitle)}</text>
  <path d="M65 138 H1725" stroke="#365b78" stroke-width="2"/>
  ${paths.join('\n  ')}
  ${keys.map(key=>node(key,t[key])).join('\n  ')}
  ${tags.join('\n  ')}
</svg>
`;
}

for (const lang of Object.keys(words)) {
  writeFileSync(join(directory, `workflow_${lang}.svg`), diagram(lang), 'utf8');
}
