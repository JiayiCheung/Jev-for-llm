"use strict";

const pad = number => String(number).padStart(2, "0");
const createdText = created => {
  const date = new Date(created * 1000);
  return Number.isFinite(date.getTime())
    ? `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}` : null;
};
window.batchTime = id => {
  const batch = (window.JEV_BATCHES || []).find(item => item.id === id);
  return batch && batch.created != null ? createdText(batch.created) : null;
};
const batchSelect = document.getElementById("experiment-batch");
if (batchSelect) {
  const batches = window.JEV_BATCHES || [];
  window.updateBatchLabels = language => {
    const selected = batchSelect.value;
    batchSelect.replaceChildren(...batches.map(batch => {
      const option = document.createElement("option");
      option.value = batch.slug;
      option.textContent = `${createdText(batch.created) || batch.id} · ${batch.modes.join(" / ")} · ${batch.tasks} ${language === "zh" ? "道题" : "tasks"}`;
      return option;
    }));
    if (batches.some(batch => batch.slug === selected)) batchSelect.value = selected;
  };
  let language = "zh";
  try { language = localStorage.getItem("jev-dashboard-language") === "en" ? "en" : "zh"; } catch (_) {}
  window.updateBatchLabels(language);
  const current = location.pathname.match(/\/batches\/([0-9a-f]{20})\/?$/);
  if (current && batches.some(batch => batch.slug === current[1])) batchSelect.value = current[1];
  else if (batches.length) batchSelect.value = batches[0].slug;
  batchSelect.onchange = () => {
    if (current && batches.some(batch => batch.slug === batchSelect.value)) {
      location.assign(`../${batchSelect.value}/`);
    }
  };
}
