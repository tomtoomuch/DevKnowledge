'use strict';

// SQLite is a local embedded metric store owned only by the Supervisor.
// No browser endpoint, MongoDB dependencies, credentials or user-provided SQL.
const { DatabaseSync } = require('node:sqlite');
const { mkdirSync } = require('node:fs');
const { dirname } = require('node:path');

const STATUS = new Set(['healthy', 'degraded', 'unavailable', 'unknown']);
const GPU_STATUS = new Set(['healthy', 'unavailable', 'disabled']);
const DEFAULT_FILE = '/var/lib/devknowledge-supervisor/metrics.sqlite3';

function checkedSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== 'object' || typeof snapshot.checked_at !== 'string' ||
      !Number.isFinite(Date.parse(snapshot.checked_at)) ||
      !Array.isArray(snapshot.services) || snapshot.services.length > 32 ||
      !snapshot.gpu || !GPU_STATUS.has(snapshot.gpu.status)) {
    throw new TypeError('Invalid monitoring snapshot');
  }
  for (const item of snapshot.services) {
    if (!item || typeof item.id !== 'string' || !/^[a-z0-9-]{1,64}$/.test(item.id) ||
        !STATUS.has(item.status)) {
      throw new TypeError('Invalid service observation');
    }
  }
  const devices = Array.isArray(snapshot.gpu.devices) ? snapshot.gpu.devices : [];
  if (devices.length > 16) throw new TypeError('Too many GPU observations');
  for (const gpu of devices) {
    if (!gpu || !Number.isInteger(gpu.index) || gpu.index < 0 || gpu.index > 128 ||
        typeof gpu.name !== 'string' || gpu.name.length > 120 ||
        ['utilization_pct', 'memory_used_mib', 'memory_total_mib', 'temperature_c']
          .some(key => gpu[key] !== null && gpu[key] !== undefined &&
            (typeof gpu[key] !== 'number' || !Number.isFinite(gpu[key])))) {
      throw new TypeError('Invalid GPU observation');
    }
  }
  const raw = JSON.stringify(snapshot);
  if (raw.length > 65536) throw new TypeError('Monitoring snapshot too large');
  return { raw, devices };
}

function openMetricsStore(filename = DEFAULT_FILE) {
  if (typeof filename !== 'string' || !filename || filename.includes('\0')) {
    throw new TypeError('Invalid metrics database path');
  }
  if (filename !== ':memory:') mkdirSync(dirname(filename), { recursive: true });
  const db = new DatabaseSync(filename, { timeout: 5000 });
  try {
    db.exec(`PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS metric_samples (
  sample_id INTEGER PRIMARY KEY,
  sampled_at TEXT NOT NULL,
  gpu_status TEXT NOT NULL CHECK(gpu_status IN ('healthy','unavailable','disabled')),
  raw_snapshot_json TEXT NOT NULL CHECK(json_valid(raw_snapshot_json))
) STRICT;
CREATE INDEX IF NOT EXISTS metric_samples_sampled_at ON metric_samples(sampled_at);
CREATE TABLE IF NOT EXISTS service_metrics (
  sample_id INTEGER NOT NULL REFERENCES metric_samples(sample_id) ON DELETE CASCADE,
  service_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('healthy','degraded','unavailable','unknown')),
  PRIMARY KEY(sample_id, service_id)
) STRICT;
CREATE TABLE IF NOT EXISTS gpu_metrics (
  sample_id INTEGER NOT NULL REFERENCES metric_samples(sample_id) ON DELETE CASCADE,
  gpu_index INTEGER NOT NULL,
  gpu_name TEXT NOT NULL,
  utilization_pct REAL,
  memory_used_mib REAL,
  memory_total_mib REAL,
  temperature_c REAL,
  PRIMARY KEY(sample_id, gpu_index)
) STRICT;`);
    const insertSample = db.prepare(
      'INSERT INTO metric_samples(sampled_at, gpu_status, raw_snapshot_json) VALUES(?, ?, ?)');
    const insertService = db.prepare(
      'INSERT INTO service_metrics(sample_id, service_id, status) VALUES(?, ?, ?)');
    const insertGpu = db.prepare(`INSERT INTO gpu_metrics(
      sample_id, gpu_index, gpu_name, utilization_pct, memory_used_mib, memory_total_mib, temperature_c
    ) VALUES(?, ?, ?, ?, ?, ?, ?)`);
    const getRecent = db.prepare(
      'SELECT sample_id, raw_snapshot_json FROM metric_samples ORDER BY sample_id DESC LIMIT ?');
    const getCount = db.prepare('SELECT count(*) AS count FROM metric_samples');
    const deleteOld = db.prepare('DELETE FROM metric_samples WHERE sampled_at < ?');

    return {
      record(snapshot) {
        const { raw, devices } = checkedSnapshot(snapshot);
        db.exec('BEGIN IMMEDIATE');
        try {
          const inserted = insertSample.run(
            new Date(snapshot.checked_at).toISOString(), snapshot.gpu.status, raw,
          );
          for (const item of snapshot.services) {
            insertService.run(inserted.lastInsertRowid, item.id, item.status);
          }
          for (const gpu of devices) {
            insertGpu.run(inserted.lastInsertRowid, gpu.index, gpu.name,
              gpu.utilization_pct ?? null, gpu.memory_used_mib ?? null,
              gpu.memory_total_mib ?? null, gpu.temperature_c ?? null);
          }
          db.exec('COMMIT');
          return Number(inserted.lastInsertRowid);
        } catch (error) {
          db.exec('ROLLBACK');
          throw error;
        }
      },
      recent(limit = 20) {
        if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
          throw new RangeError('History limit must be between 1 and 100');
        }
        return getRecent.all(limit).map(row => ({
          sample_id: Number(row.sample_id), ...JSON.parse(row.raw_snapshot_json),
        }));
      },
      count() {
        return Number(getCount.get().count);
      },
      prune(retentionDays = 90, now = Date.now()) {
        if (!Number.isInteger(retentionDays) || retentionDays < 1 || retentionDays > 3650 ||
            !Number.isFinite(now)) throw new RangeError('Invalid retention policy');
        const cutoff = new Date(now - retentionDays * 86400000).toISOString();
        return Number(deleteOld.run(cutoff).changes);
      },
      close() {
        db.close();
      },
    };
  } catch (error) {
    db.close();
    throw error;
  }
}

function samplingInterval(raw) {
  const interval = Number(raw);
  return Number.isInteger(interval) && interval >= 10000 && interval <= 3600000
    ? interval : 60000;
}

function startMetricSampling(collectSnapshot, store, {
  intervalMs = 60000,
  retentionDays = 90,
  onFailure = () => {},
} = {}) {
  let running = false;
  let stopped = false;
  let lastPrune = 0;
  async function tick() {
    if (running || stopped) return;
    running = true;
    try {
      store.record(await collectSnapshot());
      if (Date.now() - lastPrune >= 86400000) {
        store.prune(retentionDays);
        lastPrune = Date.now();
      }
    } catch (error) {
      onFailure(error instanceof Error ? error.name : 'SamplingError');
    } finally {
      running = false;
    }
  }
  const timer = setInterval(() => { void tick(); }, intervalMs);
  timer.unref();
  void tick();
  return { tick, stop() { stopped = true; clearInterval(timer); } };
}

module.exports = { openMetricsStore, checkedSnapshot, samplingInterval, startMetricSampling };
