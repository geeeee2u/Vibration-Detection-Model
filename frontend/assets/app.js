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
const ACCESS_DENIED_MESSAGE = "해당 계정으로는 접근할 수 없습니다.";
const analysisState = { rows: [], controlsBound: false };
const alarmState = { rows: [], controlsBound: false, selectedTimestamp: null };

function showError(message) {
  let target = document.querySelector("[data-api-error]");
  if (!target) {
    target = document.createElement("div"); target.dataset.apiError = "";
    target.className = "m-4 rounded border border-error bg-error-container/20 p-3 text-error";
    document.querySelector("main")?.prepend(target);
  }
  target.textContent = message;
}

function clearError() {
  document.querySelector("[data-api-error]")?.remove();
}

function downsample(rows, maximum = 1200) {
  if (rows.length <= maximum) return rows;
  const step = Math.ceil(rows.length / maximum);
  return rows.filter((_, index) => index % step === 0 || index === rows.length - 1);
}

function renderCanvasFallback(canvas, datasets) {
  const width = Math.max(canvas.clientWidth, 320);
  const height = Math.max(canvas.clientHeight, 160);
  const ratio = window.devicePixelRatio || 1;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  context.clearRect(0, 0, width, height);
  const values = datasets.flatMap(dataset => dataset.data).map(Number).filter(Number.isFinite);
  if (!values.length) {
    context.fillStyle = "#8c909f"; context.font = "14px sans-serif";
    context.fillText("선택한 표시 항목이 없습니다.", 24, 36);
    return;
  }
  const padding = { left: 48, right: 18, top: 20, bottom: 30 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  let minimum = Math.min(...values); let maximum = Math.max(...values);
  if (minimum === maximum) { minimum -= 1; maximum += 1; }
  context.strokeStyle = "#273647"; context.lineWidth = 1;
  for (let line = 0; line <= 4; line += 1) {
    const y = padding.top + (plotHeight * line / 4);
    context.beginPath(); context.moveTo(padding.left, y); context.lineTo(width - padding.right, y); context.stroke();
  }
  datasets.forEach(dataset => {
    context.strokeStyle = dataset.borderColor || "#adc6ff";
    context.lineWidth = dataset.borderWidth || 2;
    context.setLineDash(dataset.borderDash || []);
    context.beginPath();
    dataset.data.forEach((rawValue, index) => {
      const value = Number(rawValue);
      if (!Number.isFinite(value)) return;
      const x = padding.left + (plotWidth * index / Math.max(dataset.data.length - 1, 1));
      const y = padding.top + plotHeight * (maximum - value) / (maximum - minimum);
      if (index === 0) context.moveTo(x, y); else context.lineTo(x, y);
    });
    context.stroke();
  });
  context.setLineDash([]);
  context.fillStyle = "#8c909f"; context.font = "11px sans-serif";
  context.fillText(maximum.toFixed(3), 4, padding.top + 4);
  context.fillText(minimum.toFixed(3), 4, height - padding.bottom);
}

function renderChart(id, labels, datasets) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  canvas.parentElement?.querySelectorAll(":scope > :not(canvas)").forEach(element => { element.hidden = true; });
  chartInstances.get(id)?.destroy();
  if (!window.Chart) {
    chartInstances.delete(id);
    renderCanvasFallback(canvas, datasets);
    return;
  }
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

function addV2Targets() {
  const main = document.querySelector("main");
  if (!main) return;
  const page = document.body.dataset.page;
  if (page === "overview") {
    const values = main.querySelectorAll(".font-display-lg");
    ["overview-current-vibration", "overview-short-mean", "overview-score", "overview-alarm-count"].forEach((id, index) => values[index]?.setAttribute("id", id));
    const canvas = document.getElementById("vibrationChart");
    if (canvas) canvas.id = "overview-trend-chart";
    if (!document.getElementById("overview-threshold")) main.insertAdjacentHTML("beforeend", '<span id="overview-threshold" class="hidden"></span><span id="overview-status" class="hidden"></span><span id="overview-anomaly-type" class="hidden"></span>');
  }
  if (page === "analysis") {
    const tableBody = main.querySelector("tbody"); if (tableBody) tableBody.id = "analysis-rows";
  }
  if (page === "alarms") {
    const tableBody = main.querySelector("tbody"); if (tableBody) tableBody.id = "alarm-rows";
    if (!document.getElementById("alarm-detail")) main.insertAdjacentHTML("beforeend", '<aside id="alarm-detail" class="bg-surface-container-high border border-outline-variant rounded-lg"></aside>');
  }
  if (page === "performance") {
    const values = main.querySelectorAll(".font-display-lg"); values[0]?.setAttribute("id", "performance-fpr"); values[1]?.setAttribute("id", "performance-recall");
    const tableBody = main.querySelector("tbody"); if (tableBody) tableBody.id = "performance-pattern-rows";
  }
  if (page === "settings" && !document.getElementById("settings-form")) {
    main.insertAdjacentHTML("beforeend", '<form id="settings-form" class="grid grid-cols-1 md:grid-cols-2 gap-4 bg-surface-container-high border border-outline-variant rounded-lg p-6"><label>임계값 분위수<input name="threshold_quantile" type="number" step="0.001"/></label><label>경보 지속시간<input name="persistence_seconds" type="number"/></label><label>트리 수<input name="n_estimators" type="number"/></label><label>랜덤 시드<input name="random_state" type="number"/></label><label>단기 윈도우<input name="short_window" type="number"/></label><label>장기 윈도우<input name="long_window" type="number"/></label><label>기울기 윈도우<input name="slope_window" type="number"/></label><div class="md:col-span-2"><button type="submit" class="bg-primary text-on-primary px-4 py-2 rounded">설정 저장</button><button type="button" id="settings-rerun" class="ml-2 border border-outline px-4 py-2 rounded">재분석</button><p id="settings-message"></p></div></form>');
  }
}

async function loadCurrentUser() {
  try {
    return await requestJson("/api/auth/me");
  } catch (error) {
    if (String(error.message).includes("로그인이 필요")) return null;
    throw error;
  }
}

function accountLabel(user) {
  if (!user) return "로그인 필요";
  return `${user.username} · ${user.role}`;
}

function mountAccountControl(user) {
  let control = document.querySelector("[data-account-control]");
  if (!control) {
    const navigation = document.querySelector("nav");
    if (!navigation) return;
    control = document.createElement("button");
    control.type = "button";
    control.dataset.accountControl = "";
    control.className = "mt-auto mx-3 mb-3 border-t border-outline-variant pt-3 text-left text-on-surface-variant hover:text-primary";
    navigation.append(control);
  }
  control.innerHTML = `<span class="material-symbols-outlined align-middle mr-2">account_circle</span><span data-account-label>${accountLabel(user)}</span>`;
  control.onclick = () => openAccountDialog(user);
}

function openAccountDialog(user) {
  document.getElementById("account-dialog")?.remove();
  const dialog = document.createElement("div");
  dialog.id = "account-dialog";
  dialog.className = "fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4";
  dialog.innerHTML = `<section class="w-full max-w-sm rounded-xl border border-outline-variant bg-surface-container p-6 text-on-surface">
    <div class="mb-5 flex items-center justify-between"><h2 class="text-xl font-bold">계정 ${user ? "전환" : "로그인"}</h2><button type="button" data-account-close class="text-2xl">×</button></div>
    <p class="mb-4 text-sm text-on-surface-variant">${user ? `현재 로그인: ${accountLabel(user)}` : "계정으로 로그인하면 권한에 따라 기능을 사용할 수 있습니다."}</p>
    <form data-login-form class="space-y-3">
      <label class="block text-sm">ID<input name="username" required autocomplete="username" class="mt-1 w-full rounded border border-outline bg-background p-2" /></label>
      <label class="block text-sm">비밀번호<input name="password" type="password" required autocomplete="current-password" class="mt-1 w-full rounded border border-outline bg-background p-2" /></label>
      <p data-login-message class="min-h-5 text-sm text-error"></p>
      <button class="w-full rounded bg-primary p-2 font-bold text-on-primary" type="submit">로그인</button>
    </form>
    ${user ? '<button data-account-logout class="mt-3 w-full rounded border border-outline p-2">로그아웃</button>' : ""}
  </section>`;
  document.body.append(dialog);
  dialog.querySelector("[data-account-close]").onclick = () => dialog.remove();
  dialog.querySelector("[data-login-form]").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const message = dialog.querySelector("[data-login-message]");
    try {
      await requestJson("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(form))) });
      window.location.reload();
    } catch (error) { message.textContent = error.message; }
  });
  dialog.querySelector("[data-account-logout]")?.addEventListener("click", async () => {
    await requestJson("/api/auth/logout", { method: "POST" });
    window.location.href = "/";
  });
}

function showSettingsAccessDenied(user) {
  const main = document.querySelector("main");
  if (!main) return;
  const message = user ? ACCESS_DENIED_MESSAGE : "모델 설정을 사용하려면 administrator 계정으로 로그인해야 합니다.";
  main.innerHTML = `<section class="mx-auto mt-16 max-w-xl rounded-xl border border-error bg-error-container/20 p-8 text-center"><span class="material-symbols-outlined text-5xl text-error">lock</span><h2 class="mt-4 text-2xl font-bold">모델 설정 접근 제한</h2><p class="mt-3 text-on-surface-variant">${message}</p><button data-open-account-dialog class="mt-6 rounded bg-primary px-5 py-2 font-bold text-on-primary">계정 전환</button></section>`;
  main.querySelector("[data-open-account-dialog]").onclick = () => openAccountDialog(user);
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

function analysisVisibility() {
  return {
    raw: document.getElementById("analysis-show-raw")?.checked ?? true,
    moving: document.getElementById("analysis-show-moving")?.checked ?? true,
    score: document.getElementById("analysis-show-score")?.checked ?? true,
  };
}

function analysisQuery() {
  return DashboardUtils.buildRangeQuery(
    document.getElementById("analysis-start")?.value || "",
    document.getElementById("analysis-end")?.value || "",
  );
}

function initializeAnalysisRange(rows) {
  if (!rows.length) return;
  const start = document.getElementById("analysis-start");
  const end = document.getElementById("analysis-end");
  if (start && !start.value) start.value = String(rows[0].Timestamps).slice(0, 19);
  if (end && !end.value) end.value = String(rows.at(-1).Timestamps).slice(0, 19);
}

function renderAnalysis() {
  const rows = analysisState.rows;
  const sampled = downsample(rows);
  const labels = sampled.map(row => new Date(row.Timestamps).toLocaleString("ko-KR"));
  const series = DashboardUtils.selectAnalysisSeries(sampled, analysisVisibility());
  const vibrationDatasets = [];
  if (series.Vibration) vibrationDatasets.push({ label: "진동값", data: series.Vibration, borderColor: "#8c909f", pointRadius: 0, borderWidth: 1 });
  if (series.short_mean) vibrationDatasets.push({ label: "단기 이동평균", data: series.short_mean, borderColor: "#adc6ff", pointRadius: 0, borderWidth: 2 });
  if (series.long_mean) vibrationDatasets.push({ label: "장기 이동평균", data: series.long_mean, borderColor: "#ffb95f", pointRadius: 0, borderWidth: 2 });
  const scoreDatasets = [];
  if (series.anomaly_score) scoreDatasets.push({ label: "이상 점수", data: series.anomaly_score, borderColor: "#bec6e0", pointRadius: 0, borderWidth: 2 });
  if (series.threshold) scoreDatasets.push({ label: "임계값", data: series.threshold, borderColor: "#ff6961", borderDash: [5, 5], pointRadius: 0, borderWidth: 2 });
  renderChart("analysis-vibration-chart", labels, vibrationDatasets);
  renderChart("analysis-score-chart", labels, scoreDatasets);
  const target = document.getElementById("analysis-rows");
  if (target) target.innerHTML = rows.filter(row => row.raw_anomaly).slice(-100).reverse().map(row => `<tr class="border-b border-outline-variant/50 hover:bg-surface-container-high"><td class="p-4">${timestamp(row.Timestamps)}</td><td class="p-4">${row.is_anomaly ? "확정 이상" : "이상 후보"}</td><td class="p-4 text-right">${number(row.anomaly_score)}</td></tr>`).join("") || `<tr><td colspan="3" class="p-4">선택 범위의 이상 후보가 없습니다.</td></tr>`;
}

function downloadAnalysisCsv() {
  if (!analysisState.rows.length) { text("analysis-action-message", "내보낼 데이터가 없습니다."); return; }
  const columns = ["Timestamps", "Vibration", "short_mean", "long_mean", "anomaly_score", "threshold", "raw_anomaly", "confirmed_anomaly", "is_anomaly", "anomaly_type"];
  const blob = new Blob([DashboardUtils.rowsToCsv(analysisState.rows, columns)], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);
  link.href = url;
  link.download = `vibration-analysis-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  text("analysis-action-message", `${analysisState.rows.length.toLocaleString()}행을 CSV로 내보냈습니다.`);
}

async function loadAnalysis() {
  const refresh = document.getElementById("analysis-refresh");
  if (refresh) refresh.disabled = true;
  text("analysis-action-message", "데이터를 불러오는 중입니다...");
  try {
    const rows = await requestJson(`/api/analysis${analysisQuery()}`);
    analysisState.rows = rows;
    initializeAnalysisRange(rows);
    renderAnalysis();
    clearError();
    text("analysis-action-message", `${rows.length.toLocaleString()}행을 불러왔습니다.`);
  } catch (error) {
    showError(error.message);
    text("analysis-action-message", `갱신 실패: ${error.message}`);
  } finally {
    if (refresh) refresh.disabled = false;
  }
}

function bindAnalysisControls() {
  if (analysisState.controlsBound) return;
  analysisState.controlsBound = true;
  ["analysis-show-raw", "analysis-show-moving", "analysis-show-score"].forEach(id => document.getElementById(id)?.addEventListener("change", renderAnalysis));
  document.getElementById("analysis-apply-range")?.addEventListener("click", loadAnalysis);
  document.getElementById("analysis-refresh")?.addEventListener("click", loadAnalysis);
  document.getElementById("analysis-export-csv")?.addEventListener("click", downloadAnalysisCsv);
}

async function initializeAnalysis() {
  bindAnalysisControls();
  await loadAnalysis();
}

function alarmDetail(row, trendError = "") {
  return `<div class="flex h-full flex-col gap-4">
    <div class="flex items-center justify-between border-b border-outline-variant pb-3">
      <h3 class="font-title-sm text-title-sm font-bold"><span class="material-symbols-outlined mr-2 align-middle text-error">warning</span>상세 분석 정보</h3>
      <span class="inline-flex rounded border px-2 py-1 text-xs font-bold ${row.is_anomaly ? "border-error text-error" : "border-tertiary text-tertiary"}">${row.is_anomaly ? "확정 이상" : "이상 후보"}</span>
    </div>
    <div><p class="text-xs text-on-surface-variant">발생 시각</p><p data-detail-timestamp class="font-data-mono text-lg">${timestamp(row.Timestamps)}</p></div>
    <div class="grid grid-cols-2 gap-2">
      <div class="rounded border border-outline-variant bg-surface-container-low p-3"><p class="text-xs text-on-surface-variant">이상 유형</p><b>${koreanType[row.anomaly_type] || row.anomaly_type}</b></div>
      <div class="rounded border border-outline-variant bg-surface-container-low p-3"><p class="text-xs text-on-surface-variant">진동값</p><b>${number(row.Vibration)}</b></div>
      <div class="rounded border border-outline-variant bg-surface-container-low p-3"><p class="text-xs text-on-surface-variant">단기 / 장기 평균</p><b>${number(row.short_mean)} / ${number(row.long_mean)}</b></div>
      <div class="rounded border border-outline-variant bg-surface-container-low p-3"><p class="text-xs text-on-surface-variant">이상 점수 / 임계값</p><b>${number(row.anomaly_score)} / ${number(row.threshold)}</b></div>
    </div>
    <div><div class="mb-2 flex justify-between text-xs text-on-surface-variant"><span>국소 진동 트렌드 (±1분)</span><span>Score ${number(row.anomaly_score)}</span></div><div class="h-44 rounded border border-outline-variant bg-surface-container-low p-2"><canvas id="alarm-local-trend"></canvas></div>${trendError ? `<p class="mt-1 text-xs text-error">${trendError}</p>` : ""}</div>
    <div><p class="mb-2 text-xs text-on-surface-variant">주요 Feature 값</p><div class="grid grid-cols-2 gap-2 text-sm">
      <p>표준편차 <b class="float-right">${number(row.short_std)}</b></p><p>변동성 비율 <b class="float-right">${number(row.volatility_ratio)}</b></p>
      <p>변화 기울기 <b class="float-right">${number(row.slope, 5)}</b></p><p>스파이크 수 <b class="float-right">${number(row.spike_count, 0)}</b></p>
    </div></div>
    <p class="mt-auto border-l-2 border-tertiary bg-surface-container-low p-3 text-sm text-on-surface-variant">이 결과는 설비 고장 확정이 아닌 이상 후보 또는 확정 경보입니다. 실제 고장 여부는 현장 점검이 필요합니다.</p>
  </div>`;
}

async function selectAlarm(row, item) {
  const detail = document.getElementById("alarm-detail");
  if (!detail) return;
  alarmState.selectedTimestamp = row.Timestamps;
  document.querySelectorAll("[data-alarm-index]").forEach(element => {
    const selected = element === item;
    element.setAttribute("aria-selected", String(selected));
    element.classList.toggle("bg-secondary-container/30", selected);
    element.classList.toggle("border-l-2", selected);
    element.classList.toggle("border-l-primary", selected);
  });
  detail.innerHTML = alarmDetail(row);
  try {
    const trend = await requestJson(`/api/trend${DashboardUtils.buildCenteredRangeQuery(row.Timestamps, 60)}`);
    if (alarmState.selectedTimestamp !== row.Timestamps) return;
    const sampled = downsample(trend, 600);
    renderChart("alarm-local-trend", sampled.map(point => new Date(point.Timestamps).toLocaleTimeString("ko-KR")), [
      { label: "진동값", data: sampled.map(point => point.Vibration), borderColor: "#adc6ff", pointRadius: 0, borderWidth: 2 },
      { label: "단기 이동평균", data: sampled.map(point => point.short_mean), borderColor: "#ffb95f", pointRadius: 0, borderWidth: 2 },
    ]);
  } catch (error) {
    if (alarmState.selectedTimestamp !== row.Timestamps) return;
    detail.innerHTML = alarmDetail(row, `국소 트렌드를 불러오지 못했습니다: ${error.message}`);
  }
}

function renderAlarms() {
  const rows = DashboardUtils.filterAlarmRows(
    alarmState.rows,
    document.getElementById("alarm-status-filter")?.value || "all",
    document.getElementById("alarm-type-filter")?.value || "all",
  );
  const target = document.getElementById("alarm-rows");
  if (!target) return;
  target.innerHTML = rows.map((row, index) => `<tr data-alarm-index="${index}" class="hover:bg-surface-container transition-colors cursor-pointer"><td class="py-3 px-4">${timestamp(row.Timestamps)}</td><td class="py-3 px-4 text-right">${number(row.Vibration)}</td><td class="py-3 px-4 text-right">${number(row.short_mean)}</td><td class="py-3 px-4 text-right">${number(row.anomaly_score)}</td><td class="py-3 px-4 text-center">${row.is_anomaly ? "확정 이상" : "이상 후보"}</td><td class="py-3 px-4">${koreanType[row.anomaly_type] || row.anomaly_type}</td><td class="py-3 px-4"><button class="text-primary" type="button" aria-label="상세 보기"><span class="material-symbols-outlined text-base">chevron_right</span></button></td></tr>`).join("") || `<tr><td colspan="7" class="p-4">선택한 조건의 경보가 없습니다.</td></tr>`;
  const items = target.querySelectorAll("[data-alarm-index]");
  items.forEach(item => item.addEventListener("click", () => selectAlarm(rows[Number(item.dataset.alarmIndex)], item)));
  if (rows[0]) selectAlarm(rows[0], items[0]);
  else {
    alarmState.selectedTimestamp = null;
    const detail = document.getElementById("alarm-detail");
    if (detail) detail.innerHTML = '<div class="p-6 text-on-surface-variant">선택한 조건에 맞는 경보가 없습니다.</div>';
  }
}

function bindAlarmControls() {
  if (alarmState.controlsBound) return;
  alarmState.controlsBound = true;
  ["alarm-status-filter", "alarm-type-filter"].forEach(id => document.getElementById(id)?.addEventListener("change", renderAlarms));
  document.getElementById("alarm-apply-filters")?.addEventListener("click", renderAlarms);
}

async function initializeAlarms() {
  alarmState.rows = await requestJson(`/api/alarms${rangeQuery()}`);
  bindAlarmControls();
  renderAlarms();
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
  addV2Targets();
  bindNavigation();
  bindRangeButtons(() => runPage());
  try {
    const user = await loadCurrentUser();
    mountAccountControl(user);
    if (document.body.dataset.page === "settings" && user?.role !== "administrator") {
      showSettingsAccessDenied(user);
      return;
    }
    await initialize();
  } catch (error) { showError(error.message); }
}
document.addEventListener("DOMContentLoaded", runPage);
