'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { mkdtempSync, rmSync, readFileSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const { DatabaseSync } = require('node:sqlite');
const { backupMetrics } = require('../src/metrics-backup');
const { openMetricsStore } = require('../src/metrics-store');

test('online backup is consistent, verified, and never overwrites a backup', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'dk-metrics-backup-'));
  const source = join(dir, 'source.sqlite3');
  const dest = join(dir, 'backups', 'metrics.sqlite3');
  const store = openMetricsStore(source);
  try {
    store.record({ checked_at: '2026-11-10T10:00:00.000Z',
      services: [{ id: 'api-kms', status: 'healthy' }],
      gpu: { status: 'disabled', devices: [] } });
    await backupMetrics(source, dest);
    const copied = new DatabaseSync(dest, { readOnly: true });
    assert.equal(copied.prepare('PRAGMA integrity_check').get().integrity_check, 'ok');
    assert.equal(copied.prepare('SELECT count(*) AS n FROM metric_samples').get().n, 1);
    copied.close();
    const saved = readFileSync(dest);
    await assert.rejects(backupMetrics(source, dest), /already exists/);
    assert.deepEqual(readFileSync(dest), saved);
    await assert.rejects(backupMetrics(source, source), TypeError);
    assert.equal(store.count(), 1);
  } finally {
    store.close();
    rmSync(dir, { recursive: true, force: true });
  }
});
