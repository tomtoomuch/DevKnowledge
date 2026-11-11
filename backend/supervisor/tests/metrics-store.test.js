'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { mkdtempSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const { DatabaseSync } = require('node:sqlite');
const { createServer } = require('../src/server');
const {
  openMetricsStore, samplingInterval, startMetricSampling,
} = require('../src/metrics-store');

function sample(at = '2026-11-10T10:00:00.000Z') {
  return {
    checked_at: at,
    services: [
      { id: 'api-gateway', name: 'Gateway', status: 'healthy', detail: 'UP' },
      { id: 'api-kms', name: 'KMS', status: 'degraded', detail: 'Storage warning' },
    ],
    gpu: {
      status: 'healthy', devices: [
        { index: 0, name: 'Test GPU', utilization_pct: 12,
          memory_used_mib: 128, memory_total_mib: 1024, temperature_c: 45 },
      ],
    },
  };
}

test('SQLite writes normalized metrics and raw snapshots atomically, survives reopening', () => {
  const dir = mkdtempSync(join(tmpdir(), 'dk-metrics-'));
  const path = join(dir, 'supervisor.sqlite3');
  try {
    const writer = openMetricsStore(path);
    assert.equal(writer.record(sample()), 1);
    assert.equal(writer.record(sample('2026-11-10T10:01:00.000Z')), 2);
    assert.equal(writer.count(), 2);
    assert.equal(writer.recent(1)[0].sample_id, 2);
    assert.equal(writer.recent(1)[0].services[1].status, 'degraded');
    writer.close();

    const sql = new DatabaseSync(path, { readOnly: true });
    assert.equal(sql.prepare('SELECT count(*) AS n FROM service_metrics').get().n, 4);
    assert.equal(sql.prepare('SELECT count(*) AS n FROM gpu_metrics').get().n, 2);
    assert.equal(sql.prepare('SELECT status FROM service_metrics WHERE sample_id=1 AND service_id=?')
      .get('api-kms').status, 'degraded');
    assert.equal(sql.prepare('PRAGMA integrity_check').all()[0].integrity_check, 'ok');
    sql.close();

    const reopened = openMetricsStore(path);
    assert.equal(reopened.count(), 2);
    assert.equal(reopened.recent(2)[1].sample_id, 1);
    reopened.close();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('invalid samples are rejected without partial writes or unsafe SQL', () => {
  const db = openMetricsStore(':memory:');
  try {
    for (const invalid of [
      { ...sample(), checked_at: 'not-a-date' },
      { ...sample(), services: [{ id: 'api-kms', status: 'INVALID' }] },
      { ...sample(), services: [{ id: 'api-kms; DROP TABLE users', status: 'healthy' }] },
      { ...sample(), gpu: { status: 'healthy', devices: [{ index: -1, name: 'oops' }] } },
    ]) {
      assert.throws(() => db.record(invalid), TypeError);
    }
    assert.equal(db.count(), 0);
    const duplicated = sample();
    duplicated.services.push({ id: 'api-kms', status: 'healthy' });
    assert.throws(() => db.record(duplicated), /UNIQUE constraint failed/);
    assert.equal(db.count(), 0, 'rolled back entire duplicate observation');
    assert.equal(db.record(sample()), 1, 'database remains writable');
    for (const limit of [0, -1, 101, 1.5, '2']) {
      assert.throws(() => db.recent(limit), RangeError);
    }
  } finally {
    db.close();
  }
});

test('retention deletes old snapshots and cascades to normalized rows', () => {
  const db = openMetricsStore(':memory:');
  try {
    db.record(sample('2026-08-01T00:00:00.000Z'));
    db.record(sample('2026-11-09T00:00:00.000Z'));
    assert.equal(db.prune(90, Date.parse('2026-11-10T12:00:00.000Z')), 1);
    assert.equal(db.count(), 1);
    assert.equal(db.recent(1)[0].checked_at, '2026-11-09T00:00:00.000Z');
    assert.throws(() => db.prune(0), RangeError);
  } finally {
    db.close();
  }
});

test('sampling scheduler avoids overlap, stores measurements and can be stopped', async () => {
  const db = openMetricsStore(':memory:');
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  let calls = 0;
  const errors = [];
  const scheduler = startMetricSampling(async () => {
    calls += 1;
    await pending;
    return sample();
  }, db, { intervalMs: 60000, onFailure: kind => errors.push(kind) });
  try {
    await scheduler.tick(); // An active poll is not run twice.
    assert.equal(calls, 1);
    release();
    for (let i = 0; i < 30 && db.count() === 0; i++) {
      await new Promise(resolve => setTimeout(resolve, 5));
    }
    assert.equal(db.count(), 1);
    assert.deepEqual(errors, []);
    assert.equal(samplingInterval('12000'), 12000);
    assert.equal(samplingInterval('-1'), 60000);
    assert.equal(samplingInterval('NaN'), 60000);
  } finally {
    scheduler.stop();
    db.close();
  }
});

test('history route is read-only, bounded and does not expose raw database access', async () => {
  const db = openMetricsStore(':memory:');
  db.record(sample());
  const server = createServer(async () => sample(), async () => true, db);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = 'http://127.0.0.1:' + server.address().port;
  try {
    const res = await fetch(base + '/metrics/history?limit=1');
    assert.equal(res.status, 200);
    assert.equal((await res.json()).items[0].sample_id, 1);
    assert.equal((await fetch(base + '/metrics/history?limit=101')).status, 422);
    assert.equal((await fetch(base + '/metrics/history?limit=1&limit=1')).status, 404);
    assert.equal((await fetch(base + '/metrics/history?sql=DROP')).status, 404);
    assert.equal((await fetch(base + '/metrics/history', { method: 'POST' })).status, 404);
    assert.equal((await fetch(base + '/metrics')).status, 404);
    assert.equal(db.count(), 1);
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    db.close();
  }
});

test('history route refuses unauthorized callers', async () => {
  const db = openMetricsStore(':memory:');
  const server = createServer(async () => sample(), async () => false, db);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const res = await fetch('http://127.0.0.1:' + server.address().port + '/metrics/history');
    assert.equal(res.status, 404);
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    db.close();
  }
});
