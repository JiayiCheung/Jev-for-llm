import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const out = dirname(fileURLToPath(import.meta.url));
const labels = {
  zh: {
    title: 'Jev 引导的分段推理流程', subtitle: '同一题目与种子：生成 → 评分 → 决策 → 下一段',
    config: ['读取配置与评分问题', 'config.json · parameters.json'],
    task: ['编码题目', 'Qwen 聊天模板 · 提示词 token'],
    init: ['初始化当前参数', '从 initial 值建立采样映射'],
    generate: ['Qwen / vLLM 生成一段', '当前参数 · 累计 token · 分段预算'],
    score: ['Jev 评分请求', '正确性 · 相关性 · 重复性 · 完整性'],
    record: ['逐轮保存', 'result.json：请求与决策', 'answer.txt：累计答案快照'],
    continue: ['还能生成下一段吗？', '模型结束 / 可选评分停止', '或任一预算耗尽'],
    finish: ['结束本次运行', '保存最终状态与停止原因'],
    mode: ['选择实验模式', '两组均记录本段 Score'],
    fixed: ['fixed：保持参数', '下一段沿用当前采样设置'],
    gate: ['adaptive：先检查反馈', '上轮改动需回退？当前处于冷却期？'],
    hold: ['恢复或保持', '回退旧参数，或等待下一轮'],
    direction: ['Jev 选择参数动作', '按类型给出合法 Choice'],
    value: ['必要时再选具体值', '仅在需要时再次请求 Jev', '候选受边界与步长约束'],
    next: ['准备下一段', '下一轮 vLLM 请求才使用新参数'],
    no: '否', yes: '是', fallback: '回退 / 冷却', ready: '可调整',
    required: '需要选值',
    note: '评分针对已经生成的文字；回退只恢复参数，不撤销文字。',
  },
  en: {
    title: 'Jev-guided segmented inference', subtitle: 'One task and seed: generate → score → decide → next segment',
    config: ['Load config and Score questions', 'config.json · parameters.json'],
    task: ['Encode the task', 'Qwen chat template · prompt tokens'],
    init: ['Initialize parameters', 'Build sampling map from initial values'],
    generate: ['Qwen / vLLM segment', 'Current settings · tokens · budget'],
    score: ['Request Jev Scores', 'Correctness · relevance · repetition · completeness'],
    record: ['Save every round', 'result.json: requests and decisions', 'answer.txt: cumulative answers'],
    continue: ['Can another segment run?', 'Model or optional Score stop', 'Or any budget exhausted'],
    finish: ['Finish this run', 'Save final status and stop reason'],
    mode: ['Select experiment mode', 'Both modes record segment Scores'],
    fixed: ['fixed: keep parameters', 'Reuse settings next segment'],
    gate: ['adaptive: inspect feedback first', 'Rollback last change? In a cooldown round?'],
    hold: ['Restore or keep', 'Revert or defer changes'],
    direction: ['Jev selects actions', 'Legal type-specific Choices'],
    value: ['Choose exact values', 'Extra Jev Choice if needed', 'Bounded step candidates'],
    next: ['Prepare the next segment', 'New settings reach the next vLLM request'],
    no: 'No', yes: 'Yes', fallback: 'rollback / cooldown', ready: 'ready to adjust',
    required: 'value needed',
    note: 'Scores describe text already generated; rollback restores settings, not text.',
  },
};

const esc = s => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const rect = (x,y,w,h,kind='normal') => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="20" class="box ${kind}"/>`;
const lines = (x,y,w,h,items,kind='normal') => {
  const titleY = y + (items.length === 3 ? 36 : 42);
  return `<text x="${x+w/2}" y="${titleY}" text-anchor="middle" class="box-title ${kind}">${esc(items[0])}</text>` +
    items.slice(1).map((s,i) => `<text x="${x+w/2}" y="${titleY+35+i*28}" text-anchor="middle" class="box-detail">${esc(s)}</text>`).join('');
};
const box = (x,y,w,h,items,kind='normal') => rect(x,y,w,h,kind)+lines(x,y,w,h,items,kind);
const path = (d,extra='') => `<path d="${d}" class="arrow ${extra}" marker-end="url(#head)"/>`;
const tag = (x,y,s) => `<text x="${x}" y="${y}" class="tag">${esc(s)}</text>`;

function make(lang) {
  const t=labels[lang];
  const nodes = [
    box(70,160,400,106,t.config), box(600,160,400,106,t.task), box(1130,160,400,106,t.init),
    box(590,334,420,110,t.generate,'emphasis'), box(590,492,420,110,t.score,'jev'),
    box(70,492,400,110,t.record), box(590,655,420,96,t.continue,'decision'),
    box(70,655,400,96,t.finish), box(590,804,420,96,t.mode,'decision'),
    box(70,950,400,118,t.fixed), box(1080,950,450,118,t.gate,'decision'),
    box(850,1115,300,110,t.hold), box(1220,1115,310,110,t.direction,'jev'),
    box(1220,1265,310,110,t.value,'jev'), box(590,1405,420,100,t.next,'emphasis'),
  ];
  const paths = [
    path('M470 213 H600'), path('M1000 213 H1130'),
    path('M1330 266 V304 H800 V334'), path('M800 444 V492'),
    path('M590 547 H470','side'), path('M800 602 V655'),
    path('M590 703 H470','side'), path('M800 751 V804'),
    path('M590 852 H510 V1009 H470'), path('M1010 852 H1040 V1009 H1080'),
    path('M1140 1068 V1088 H1000 V1115'),
    path('M1370 1068 V1115'),
    path('M1375 1225 V1265'),
    path('M270 1068 V1455 H590'),
    path('M1000 1225 V1360 H800 V1405'),
    path('M1530 1170 H1555 V1455 H1010'),
    path('M1375 1375 V1390 H1050 V1455 H1010'),
    path('M800 1505 V1538 H1580 V389 H1010','loop'),
  ];
  const tags = [tag(505,688,t.no),tag(817,784,t.yes),tag(932,1097,t.fallback),tag(1360,1097,t.ready),
    tag(1380,1248,t.required)];
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 1560" role="img" aria-labelledby="title desc">
  <title id="title">${esc(t.title)}</title>
  <desc id="desc">${esc(t.subtitle)}. ${esc(t.note)}</desc>
  <defs>
    <marker id="head" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto"><path d="M1 1 L10 6 L1 11" fill="none" stroke="#7fa9c7" stroke-width="1.8"/></marker>
  </defs>
  <style>
    .box { fill:#10243b; stroke:#315878; stroke-width:2; }
    .box.emphasis { fill:#10385a; stroke:#3986b5; }
    .box.jev { fill:#10334a; stroke:#25a3b7; }
    .box.decision { fill:#0b1e32; stroke:#609ac0; stroke-dasharray:6 5; }
    .box-title { fill:#e6f3ff; font:700 25px Arial,'Microsoft YaHei',sans-serif; }
    .box-title.emphasis,.box-title.jev { fill:#a5dfff; }
    .box-detail { fill:#b3c8d9; font:20px Arial,'Microsoft YaHei',sans-serif; }
    .arrow { fill:none; stroke:#7fa9c7; stroke-width:2.5; stroke-linecap:round; stroke-linejoin:round; }
    .arrow.side { stroke:#607f9b; }.arrow.loop { stroke:#46afd0; stroke-width:3; }
    .tag { fill:#8bd1f4; font:700 19px Arial,'Microsoft YaHei',sans-serif; }
  </style>
  <rect width="1600" height="1560" rx="24" fill="#091522"/>
  <text x="70" y="72" fill="#e9f5ff" font-family="Arial,'Microsoft YaHei',sans-serif" font-size="44" font-weight="700">${esc(t.title)}</text>
  <text x="72" y="113" fill="#9ebbd0" font-family="Arial,'Microsoft YaHei',sans-serif" font-size="22">${esc(t.subtitle)}</text>
  <path d="M70 131 H1530" stroke="#315878" stroke-width="2"/>
  ${paths.join('\n  ')}
  ${nodes.join('\n  ')}
  ${tags.join('\n  ')}
  <text x="70" y="1540" fill="#8eaabf" font-family="Arial,'Microsoft YaHei',sans-serif" font-size="17">${esc(t.note)}</text>
</svg>
`;
}

for (const lang of Object.keys(labels)) writeFileSync(join(out, `workflow_${lang}.svg`), make(lang), 'utf8');
