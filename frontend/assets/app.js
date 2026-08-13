const koreanType = {
  gradual_increase: "서서히 증가", increase_1_to_5pct: "1~5% 증가",
  std_increase: "표준편차 증가", repeated_spike: "반복 스파이크",
  general_anomaly: "일반 이상", independent_random: "독립 랜덤 이상", normal: "정상",
};
const koreanStatus = { normal: "정상", raw_candidate: "이상 후보", confirmed_anomaly: "확정 이상" };

async function requestJson(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "데이터를 불러오지 못했습니다.");
  return payload;
}
const number = (value, digits = 3) => value == null || Number.isNaN(Number(value)) ? "-" : Number(value).toFixed(digits);
const percent = value => value == null ? "-" : `${(Number(value) * 100).toFixed(2)}%`;
const timestamp = value => value ? new Date(value).toLocaleString("ko-KR") : "-";
const text = (id, value) => { const element = document.getElementById(id); if (element) element.textContent = value; };
const chartInstances = new Map();

function showError(message) {
  let target = document.querySelector("[data-api-error]");
  if (!target) {
    target = document.createElement("div"); target.dataset.apiError = "";
    target.className = "m-4 rounded border border-error bg-error-container/20 p-3 text-error";
    document.querySelector("main")?.prepend(target);
  }
  target.textContent = message;
}

function downsample(rows, maximum = 1200) {
  if (rows.length <= maximum) return rows;
  const step = Math.ceil(rows.length / maximum);
  return rows.filter((_, index) => index % step === 0 || index === rows.length - 1);
}

function renderChart(id, labels, datasets) {
  const canvas = document.getElementById(id);
  if (!canvas || !window.Chart) return;
  canvas.parentElement?.querySelectorAll(":scope > :not(canvas)").forEach(element => { element.hidden = true; });
  chartInstances.get(id)?.destroy();
  chartInstances.set(id, new Chart(canvas, {
    type: "line", data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { labels: { color: "#d4e4fa" } } },
      scales: { x: { ticks: { color: "#8c909f", maxTicksLimit: 8 }, grid: { color: "#273647" } }, y: { ticks: { color: "#8c909f" }, grid: { color: "#273647" } } },
    },
  }));
}

function rangeQuery() {
  const minutes = Number(document.body.dataset.rangeMinutes || 0);
  if (!minutes) return "";
  const end = document.body.dataset.latestTimestamp ? new Date(document.body.dataset.latestTimestamp) : new Date();
  const start = new Date(end.getTime() - minutes * 60_000);
  return `?${new URLSearchParams({ start: start.toISOString(), end: end.toISOString() })}`;
}

function bindRangeButtons(reload) {
  const ranges = { "최근 1분": 1, "5분": 5, "30분": 30, "1시간": 60, "전체": 0 };
  document.querySelectorAll("button").forEach(button => {
    const minutes = ranges[button.textContent.trim()];
    if (minutes === undefined) return;
    button.addEventListener("click", () => { document.body.dataset.rangeMinutes = String(minutes); reload(); });
  });
}

function bindNavigation() {
  const routes = {
    "개요": "/",
    "진동 분석": "/analysis",
    "알람 내역": "/alarms",
    "알람 이력": "/alarms",
    "경보 이력": "/alarms",
    "성능 평가": "/performance",
    "모델 설정": "/settings",
  };
  document.querySelectorAll("nav a, aside a").forEach(link => {
    const route = Object.entries(routes).find(([label]) => link.textContent.includes(label))?.[1];
    if (route) link.href = route;
  });
}

async function initializeOverview() {
  const query = rangeQuery();
  const [overview, trend] = await Promise.all([requestJson(`/api/overview${query}`), requestJson(`/api/trend${query}`)]);
  if (!overview.latest) { showError("선택한 시간 범위에 데이터가 없습니다."); return; }
  const latest = overview.latest;
  document.body.dataset.latestTimestamp = latest.Timestamps;
  text("overview-current-vibration", number(latest.Vibration));
  text("overview-short-mean", number(latest.short_mean));
  text("overview-score", number(latest.anomaly_score));
  text("overview-threshold", `임계값 ${number(latest.threshold)} · 차이 ${number(latest.anomaly_score - latest.threshold)}`);
  text("overview-alarm-count", `${overview.confirmed_alarm_count}건`);
  text("overview-status", `${koreanStatus[latest.status]}${latest.anomaly_type !== "normal" ? ` · ${koreanType[latest.anomaly_type] || latest.anomaly_type}` : ""}`);
  text("overview-anomaly-type", `유형: ${koreanType[latest.anomaly_type] || latest.anomaly_type}`);
  const rows = downsample(trend);
  renderChart("overview-trend-chart", rows.map(row => new Date(row.Timestamps).toLocaleTimeString("ko-KR")), [
    { label: "현재 진동값", data: rows.map(row => row.Vibration), borderColor: "#adc6ff", pointRadius: 0, borderWidth: 2 },
    { label: "단기 이동평균", data: rows.map(row => row.short_mean), borderColor: "#004395", pointRadius: 0, borderWidth: 2 },
    { label: "이상 후보", data: rows.map(row => row.raw_anomaly && !row.is_anomaly ? row.Vibration : null), borderColor: "#ffb95f", backgroundColor: "#ffb95f", showLine: false, pointRadius: 4 },
    { label: "확정 경보", data: rows.map(row => row.is_anomaly ? row.Vibration : null), borderColor: "#ff6961", backgroundColor: "#ff6961", showLine: false, pointRadius: 5 },
  ]);
}

function contribution(row) {
  if (row.anomaly_type === "repeated_spike") return "Spike Count";
  if (row.anomaly_type === "std_increase") return "Volatility Ratio";
  if (row.anomaly_type === "gradual_increase") return "Slope";
  return "Isolation Forest 점수";
}

async function initializeAnalysis() {
  const rows = await requestJson(`/api/analysis${rangeQuery()}`);
  const sampled = downsample(rows);
  renderChart("analysis-trend-chart", sampled.map(row => new Date(row.Timestamps).toLocaleTimeString("ko-KR")), [
    { label: "진동값", data: sampled.map(row => row.Vibration), borderColor: "#adc6ff", pointRadius: 0 },
    { label: "단기 이동평균", data: sampled.map(row => row.short_mean), borderColor: "#004395", pointRadius: 0 },
    { label: "이상 점수", data: sampled.map(row => row.anomaly_score), borderColor: "#ffb95f", pointRadius: 0 },
    { label: "임계값", data: sampled.map(row => row.threshold), borderColor: "#ff6961", borderDash: [5, 5], pointRadius: 0 },
  ]);
  const target = document.getElementById("analysis-rows");
  if (target) target.innerHTML = rows.filter(row => row.raw_anomaly).slice(-100).reverse().map(row => `<tr class="border-b border-outline-variant/50 hover:bg-surface-container-high"><td class="p-4">${timestamp(row.Timestamps)}</td><td class="p-4">${row.is_anomaly ? "확정 이상" : "이상 후보"}</td><td class="p-4">${contribution(row)}</td><td class="p-4">${number(row.anomaly_score)}</td><td class="p-4 text-right">현장 확인</td></tr>`).join("") || `<tr><td colspan="5" class="p-4">선택 범위의 이상 후보가 없습니다.</td></tr>`;
}

function alarmDetail(row) {
  return `<div class="p-6 space-y-5"><h3 class="font-title-sm text-title-sm">이벤트 상세</h3><div><span class="inline-flex rounded border px-2 py-1 ${row.is_anomaly ? "border-error text-error" : "border-tertiary text-tertiary"}">${row.is_anomaly ? "확정 이상" : "이상 후보"}</span><p class="mt-2 font-data-mono">${timestamp(row.Timestamps)}</p></div><div class="grid grid-cols-2 gap-3"><div class="rounded border border-outline-variant p-3"><p class="text-on-surface-variant">이상 점수</p><b>${number(row.anomaly_score)}</b><p class="text-on-surface-variant">임계값 ${number(row.threshold)}</p></div><div class="rounded border border-outline-variant p-3"><p class="text-on-surface-variant">진동값</p><b>${number(row.Vibration)}</b><p class="text-on-surface-variant">단기 평균 ${number(row.short_mean)}</p></div></div><p class="text-on-surface-variant">유형: ${koreanType[row.anomaly_type] || row.anomaly_type}</p><p class="border-l-2 border-tertiary p-3">이 경보는 분석 후보 또는 확정 경보이며, 실제 설비 고장 여부는 현장 확인이 필요합니다.</p></div>`;
}

async function initializeAlarms() {
  const rows = await requestJson(`/api/alarms${rangeQuery()}`);
  const target = document.getElementById("alarm-rows");
  const detail = document.getElementById("alarm-detail");
  if (!target) return;
  target.innerHTML = rows.map((row, index) => `<tr data-alarm-index="${index}" class="hover:bg-surface-container transition-colors cursor-pointer"><td class="py-3 px-4">${timestamp(row.Timestamps)}</td><td class="py-3 px-4 text-right">${number(row.Vibration)}</td><td class="py-3 px-4 text-right">${number(row.short_mean)}</td><td class="py-3 px-4 text-right">${number(row.anomaly_score)}</td><td class="py-3 px-4 text-right">${number(row.threshold)}</td><td class="py-3 px-4 text-center">${row.is_anomaly ? "확정 이상" : "이상 후보"}</td><td class="py-3 px-4">${koreanType[row.anomaly_type] || row.anomaly_type}</td></tr>`).join("") || `<tr><td colspan="7" class="p-4">선택 범위의 경보가 없습니다.</td></tr>`;
  const select = row => { if (detail) detail.innerHTML = alarmDetail(row); };
  target.querySelectorAll("[data-alarm-index]").forEach(item => item.addEventListener("click", () => select(rows[Number(item.dataset.alarmIndex)])));
  if (rows[0]) select(rows[0]);
}

async function initializePerformance() {
  const data = await requestJson("/api/performance");
  text("performance-fpr", percent(data.normal_false_positive_rate));
  text("performance-recall", percent(data.overall_recall));
  const target = document.getElementById("performance-pattern-rows");
  if (target) target.innerHTML = data.patterns.map(pattern => `<tr class="border-b border-outline-variant"><td class="p-3">${koreanType[pattern.anomaly_type] || pattern.anomaly_type}</td><td class="p-3 text-right">${pattern.rows}</td><td class="p-3 text-right">${pattern.detected_rows}</td><td class="p-3 text-right">${percent(pattern.recall)}</td><td class="p-3 text-center">${pattern.recall >= .8 ? "우수" : "검토 필요"}</td></tr>`).join("");
}

function supportedSettings(form) {
  return Object.fromEntries(["threshold_quantile", "persistence_seconds", "n_estimators", "random_state", "short_window", "long_window", "slope_window"].map(name => [name, Number(form.elements[name].value)]));
}

async function initializeSettings() {
  const settings = await requestJson("/api/settings");
  const form = document.getElementById("settings-form");
  if (!form) return;
  Object.entries(settings).forEach(([name, value]) => { const input = form.elements[name]; if (input) input.value = value; });
  form.querySelectorAll("input:not([name]), input[type=checkbox]").forEach(input => { input.disabled = true; input.setAttribute("aria-disabled", "true"); });
  const message = value => text("settings-message", value);
  form.addEventListener("submit", async event => { event.preventDefault(); await requestJson("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(supportedSettings(form)) }); message("설정을 저장했습니다."); });
  const rerun = document.getElementById("settings-rerun");
  if (rerun) rerun.addEventListener("click", async () => { rerun.disabled = true; message("재분석 중입니다..."); try { const result = await requestJson("/api/reanalyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(supportedSettings(form)) }); message(`재분석 완료: ${result.rows.toLocaleString()}행 · 확정 경보 ${result.confirmed_alarm_count}건 · FPR ${percent(result.performance.normal_false_positive_rate)}`); } finally { rerun.disabled = false; } });
}

async function runPage() {
  const initializers = { overview: initializeOverview, analysis: initializeAnalysis, alarms: initializeAlarms, performance: initializePerformance, settings: initializeSettings };
  const initialize = initializers[document.body.dataset.page];
  if (!initialize) return;
  bindNavigation();
  bindRangeButtons(() => runPage());
  try { await initialize(); } catch (error) { showError(error.message); }
}
document.addEventListener("DOMContentLoaded", runPage);
