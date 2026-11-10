'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { collectGpuMetrics, parseNvidiaSmi, QUERY, FORMAT } = require('../src/gpu');
const { createServer } = require('../src/server');
const { createSnapshotCollector, gatewayPort } = require('../src/snapshot');

test('parses multiple NVIDIA GPUs and nullable sensors', () => {
  const items = parseNvidiaSmi(
    '0, NVIDIA RTX 4060, 68, 4096, 8192, 64\n' +
    '1, "NVIDIA, CUDA", N/A, 200, 24576, [Not Supported]\n',
  );
  assert.equal(items.length, 2);
  assert.equal(items[0].utilization_pct, 68);
  assert.equal(items[1].name, 'NVIDIA, CUDA');
  assert.equal(items[1].temperature_c, null);
});

test('GPU command has fixed arguments and never uses a shell', async () => {
  const runner = async (exe, args, opts) => {
    assert.equal(exe, 'nvidia-smi');
    assert.deepEqual(args, [QUERY, FORMAT]);
    assert.equal(opts.timeout, 3000);
    return { stdout: '0, NVIDIA Test, 12, 512, 4096, 47\n' };
  };
  assert.equal((await collectGpuMetrics(runner)).devices[0].memory_used_mib, 512);
});
test('GPU absence is safe', async () => {
  assert.deepEqual(await collectGpuMetrics(async () => { throw Error('secret'); }),
    { status: 'unavailable', devices: [] });
});
test('rejects malformed and out-of-range GPU fields', () => {
  assert.throws(() => parseNvidiaSmi('0, GPU, 101, 0, 4000, 40'));
  assert.throws(() => parseNvidiaSmi('0, GPU, 45, 4001, 4000, 40'));
  assert.throws(() => parseNvidiaSmi('oops'));
});
test('validates internal Gateway port', () => {
  assert.equal(gatewayPort('3001'), 3001);
  assert.equal(gatewayPort('abc'), 3000);
  assert.equal(gatewayPort('-1'), 3000);
});

function simulated({ gateway = 200, live = 200, ready = 200, gpuEnabled = false } = {}) {
  const requested = [];
  const probe = async url => {
    requested.push(url);
    if (url === 'http://api-gateway:3107/health/frontend') {
      return { status: 200, data: { status: 'ok', service: 'frontend' } };
    }
    if (url === 'http://api-gateway:3107/health') {
      return { status: gateway, data: gateway === 200 ? { status: 'ok', service: 'api-gateway' } : null };
    }
    if (url === 'http://api-kms:8000/health') {
      return { status: live, data: live === 200 ? { status: 'ok', service: 'api-kms' } : null };
    }
    if (url === 'http://api-kms:8000/health/ready') {
      return { status: ready, data: ready === 200 ?
        { status: 'ok', service: 'api-kms', dependency: 'mongodb' } :
        { status: 'error', service: 'api-kms', dependency: 'mongodb' } };
    }
    throw Error('unexpected probe destination');
  };
  const gpu = async () => ({ status: 'ok', devices: [
    { index: 0, name: 'RTX', utilization_pct: 75, memory_used_mib: 3,
      memory_total_mib: 8, temperature_c: 45 },
  ] });
  const collect = createSnapshotCollector({ probe, gpu, gpuEnabled: () => gpuEnabled, port: () => 3107 });
  return { collect, requested };
}

test('centralizes service probes and optional GPU in one snapshot', async () => {
  const { collect, requested } = simulated({ gpuEnabled: true });
  const snapshot = await collect();
  assert.ok(snapshot.checked_at.endsWith('Z'));
  assert.deepEqual(Object.fromEntries(snapshot.services.map(s => [s.id, s.status])), {
    'api-gateway': 'healthy', frontend: 'healthy', 'api-kms': 'healthy',
    mongodb: 'healthy', collector: 'healthy',
  });
  assert.equal(snapshot.gpu.status, 'healthy');
  assert.equal(snapshot.gpu.devices[0].utilization_pct, 75);
  assert.deepEqual(requested.sort(), [
    'http://api-gateway:3107/health', 'http://api-gateway:3107/health/frontend', 'http://api-kms:8000/health',
    'http://api-kms:8000/health/ready',
  ].sort());
});

test('Mongo failure degrades KMS, never lies about Gateway', async () => {
  const snapshot = await simulated({ ready: 503 }).collect();
  assert.equal(snapshot.services.find(s => s.id === 'api-kms').status, 'degraded');
  assert.equal(snapshot.services.find(s => s.id === 'mongodb').status, 'unavailable');
  assert.equal(snapshot.services.find(s => s.id === 'api-gateway').status, 'healthy');
  assert.equal(snapshot.gpu.status, 'disabled');
});
test('when KMS is down, MongoDB is unknown rather than unavailable', async () => {
  const snapshot = await simulated({ live: 0, ready: 0 }).collect();
  assert.equal(snapshot.services.find(s => s.id === 'api-kms').status, 'unavailable');
  assert.equal(snapshot.services.find(s => s.id === 'mongodb').status, 'unknown');
});
test('a failed Gateway probe cannot be reported healthy', async () => {
  const snapshot = await simulated({ gateway: 0 }).collect();
  assert.equal(snapshot.services.find(s => s.id === 'api-gateway').status, 'unavailable');
});

test('collector exposes only read-only internal health and snapshot routes', async () => {
  const server = createServer(async () => simulated({ gpuEnabled: true }).collect());
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = 'http://127.0.0.1:' + server.address().port;
  try {
    const health = await fetch(base + '/health');
    assert.deepEqual(await health.json(), { status: 'ok', service: 'collector' });
    const response = await fetch(base + '/snapshot');
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    assert.equal((await response.json()).gpu.status, 'healthy');
    assert.equal((await fetch(base + '/metrics')).status, 404);
    assert.equal((await fetch(base + '/snapshot', { method: 'POST' })).status, 404);
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
});
