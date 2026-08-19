const test = require("node:test");
const assert = require("node:assert/strict");

const {
  buildRangeQuery,
  filterAlarmRows,
  selectAnalysisSeries,
  rowsToCsv,
  buildCenteredRangeQuery,
} = require("../frontend/assets/dashboard-utils.js");

test("buildRangeQuery sends the selected start and end values", () => {
  assert.equal(
    buildRangeQuery("2026-07-11T00:00", "2026-07-12T00:00"),
    "?start=2026-07-11T00%3A00&end=2026-07-12T00%3A00",
  );
});

test("buildRangeQuery rejects an incomplete or reversed range", () => {
  assert.throws(() => buildRangeQuery("2026-07-11T00:00", ""), /시작과 종료/);
  assert.throws(
    () => buildRangeQuery("2026-07-12T00:00", "2026-07-11T00:00"),
    /종료 일시/,
  );
});

test("selectAnalysisSeries reflects each chart checkbox", () => {
  const rows = [{ Vibration: 1.2, short_mean: 1.1, long_mean: 1.0, anomaly_score: 0.8, threshold: 0.7 }];

  assert.deepEqual(
    Object.keys(selectAnalysisSeries(rows, { raw: true, moving: false, score: false })),
    ["Vibration"],
  );
  assert.deepEqual(
    Object.keys(selectAnalysisSeries(rows, { raw: false, moving: true, score: true })),
    ["short_mean", "long_mean", "anomaly_score", "threshold"],
  );
});

test("filterAlarmRows distinguishes candidates, confirmed alarms, and types", () => {
  const rows = [
    { raw_anomaly: true, is_anomaly: false, anomaly_type: "gradual_increase" },
    { raw_anomaly: true, is_anomaly: true, anomaly_type: "repeated_spike" },
    { raw_anomaly: true, is_anomaly: true, anomaly_type: "std_increase" },
  ];

  assert.deepEqual(filterAlarmRows(rows, "candidate", "all"), [rows[0]]);
  assert.deepEqual(filterAlarmRows(rows, "confirmed", "repeated_spike"), [rows[1]]);
  assert.deepEqual(filterAlarmRows(rows, "all", "std_increase"), [rows[2]]);
});

test("rowsToCsv exports selected rows with CSV escaping", () => {
  const csv = rowsToCsv(
    [{ Timestamps: "2026-07-11T00:00:00", anomaly_type: "spike, repeated" }],
    ["Timestamps", "anomaly_type"],
  );

  assert.equal(
    csv,
    '\uFEFFTimestamps,anomaly_type\r\n2026-07-11T00:00:00,"spike, repeated"',
  );
});

test("buildCenteredRangeQuery requests one minute around the selected alarm", () => {
  assert.equal(
    buildCenteredRangeQuery("2026-07-11T12:00:00", 60),
    "?start=2026-07-11T11%3A59%3A00&end=2026-07-11T12%3A01%3A00",
  );
});
