(function exposeDashboardUtils(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.DashboardUtils = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createDashboardUtils() {
  function buildRangeQuery(start, end) {
    if (!start && !end) return "";
    if (!start || !end) throw new Error("시작과 종료 일시를 모두 입력해 주세요.");
    const startDate = new Date(start);
    const endDate = new Date(end);
    if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
      throw new Error("유효한 날짜와 시간을 입력해 주세요.");
    }
    if (startDate > endDate) throw new Error("종료 일시는 시작 일시보다 늦어야 합니다.");
    return `?${new URLSearchParams({ start, end }).toString()}`;
  }

  function selectAnalysisSeries(rows, visibility) {
    const series = {};
    if (visibility.raw) series.Vibration = rows.map(row => row.Vibration);
    if (visibility.moving) {
      series.short_mean = rows.map(row => row.short_mean);
      series.long_mean = rows.map(row => row.long_mean);
    }
    if (visibility.score) {
      series.anomaly_score = rows.map(row => row.anomaly_score);
      series.threshold = rows.map(row => row.threshold);
    }
    return series;
  }

  function filterAlarmRows(rows, status = "all", type = "all") {
    return rows.filter(row => {
      const statusMatches = status === "all"
        || (status === "candidate" && row.raw_anomaly && !row.is_anomaly)
        || (status === "confirmed" && row.is_anomaly);
      const typeMatches = type === "all" || row.anomaly_type === type;
      return statusMatches && typeMatches;
    });
  }

  function localTimestamp(date) {
    const pad = value => String(value).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  }

  function buildCenteredRangeQuery(timestamp, seconds = 60) {
    const center = new Date(timestamp);
    if (Number.isNaN(center.getTime())) throw new Error("유효한 알람 발생 시각이 아닙니다.");
    const offset = Number(seconds) * 1000;
    return buildRangeQuery(
      localTimestamp(new Date(center.getTime() - offset)),
      localTimestamp(new Date(center.getTime() + offset)),
    );
  }

  function csvCell(value) {
    const text = value == null ? "" : String(value);
    return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  }

  function rowsToCsv(rows, columns) {
    const lines = [columns.map(csvCell).join(",")];
    rows.forEach(row => lines.push(columns.map(column => csvCell(row[column])).join(",")));
    return `\uFEFF${lines.join("\r\n")}`;
  }

  return { buildRangeQuery, buildCenteredRangeQuery, selectAnalysisSeries, filterAlarmRows, rowsToCsv };
});
