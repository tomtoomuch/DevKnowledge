'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { collectGpuMetrics, parseNvidiaSmi, QUERY, FORMAT } = require('../src/collector');
const { createServer } = require('../src/server');

test('parses multiple NVIDIA GPUs and unsupported metrics', () => {
  const items = parseNvidiaSmi(
    '0, NVIDIA RTX 4060, 68, 4096, 8192, 64\n' +
    '1, "NVIDIA, CUDA", N/A, 200, 24576, [Not Supported]\n',
  );
  assert.equal(items.length, 2);
  assert.equal(items[0].utilization_pct, 68);
  assert.equal(items[1].name, 'NVIDIA, CUDA');
  assert.equal(items[1].temperature_c, null);
  assert.equal(items[1].utilization_pct, null);
});

test('smi command uses fixed arguments and never a shell', async () => {
  const runner = async (exe, args, opts) => {
    assert.equal(exe, 'nvidia-smi');
    assert.deepEqual(args, [QUERY, FORMAT]);
    assert.equal(opts.timeout, 3000);
    assert.equal(opts.maxBuffer, 65536);
    return { stdout: '0, NVIDIA Test, 12, 512, 4096, 47\n' };
  };
  const output = await collectGpuMetrics(runner);
  assert.equal(output.status, 'ok');
  assert.equal(output.devices[0].memory_used_mib, 512);
});

test('an absent NVIDIA driver returns unavailable, not fake values', async () => {
  const result = await collectGpuMetrics(async () => { throw new Error('private driver path'); });
  assert.deepEqual(result, { status: 'unavailable', devices: [] });
});

test('rejects malformed or out-of-range data', () => {
  assert.throws(() => parseNvidiaSmi('0, GPU, 101, 0, 4000, 40'));
  assert.throws(() => parseNvidiaSmi('0, GPU, 45, 4001, 4000, 40'));
  assert.throws(() => parseNvidiaSmi('oops'));
  assert.throws(() => parseNvidiaSmi('0, GPU, 45, 1, 4000, 40\n0, GPU, 50, 2, 4000, 40'));
});

test('only fixed GET endpoints are exposed', async () => {
  const server = createServer(async () => ({
    status: 'ok', devices: [{ index: 0, name: 'test', utilization_pct: 1,
      memory_used_mib: 100, memory_total_mib: 1000, temperature_c: 50 }],
  }));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + server.address().port;
  try {
    const health = await fetch(origin + '/health');
    assert.equal(health.status, 200);
    const metrics = await fetch(origin + '/metrics');
    assert.equal(metrics.status, 200);
    const body = await metrics.json();
    assert.equal(body.devices[0].name, 'test');
    assert.equal(metrics.headers.get('cache-control'), 'no-store');
    assert.equal((await fetch(origin + '/other')).status, 404);
    assert.equal((await fetch(origin + '/metrics', { method: 'POST' })).status, 404);
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
});
