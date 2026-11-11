'use strict';

// Administrative CLI only: creates a consistent SQLite online snapshot.
// Never copy a live .sqlite3 file directly while WAL mode is active.
const { backup, DatabaseSync } = require('node:sqlite');
const { randomUUID } = require('node:crypto');
const {
  existsSync, mkdirSync, chmodSync, linkSync, unlinkSync,
} = require('node:fs');
const { isAbsolute, dirname, basename, join, resolve } = require('node:path');

async function backupMetrics(source, destination) {
  if (typeof source !== 'string' || typeof destination !== 'string' ||
      !isAbsolute(source) || !isAbsolute(destination) ||
      source.includes('\0') || destination.includes('\0') ||
      resolve(source) === resolve(destination)) {
    throw new TypeError('Source and destination must be distinct absolute paths');
  }
  if (existsSync(destination)) throw new Error('Backup target already exists');
  mkdirSync(dirname(destination), { recursive: true });
  const temp = join(dirname(destination), '.' + basename(destination) + '.' + randomUUID() + '.part');
  let sourceDb;
  try {
    sourceDb = new DatabaseSync(source, { readOnly: true });
    await backup(sourceDb, temp);
    const check = new DatabaseSync(temp, { readOnly: true });
    try {
      if (check.prepare('PRAGMA integrity_check').get().integrity_check !== 'ok') {
        throw new Error('Backup failed SQLite integrity check');
      }
    } finally {
      check.close();
    }
    chmodSync(temp, 0o600);
    // Atomic no-clobber creation even if another operator chose the same path.
    linkSync(temp, destination);
  } finally {
    sourceDb?.close();
    if (existsSync(temp)) unlinkSync(temp);
  }
  return destination;
}

if (require.main === module) {
  const source = process.env.METRICS_DB_PATH ||
    '/var/lib/devknowledge-supervisor/metrics.sqlite3';
  const target = process.argv[2];
  backupMetrics(source, target)
    .then(path => process.stdout.write('Verified SQLite backup: ' + path + '\n'))
    .catch(() => {
      // Do not print source database path, credentials or a raw exception.
      process.stderr.write('SQLite backup refused or failed; source unchanged.\n');
      process.exitCode = 1;
    });
}

module.exports = { backupMetrics };
