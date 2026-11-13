const test = require('node:test');
const assert = require('node:assert/strict');
const { peerAllowed } = require('../src/peer-guard');

test('Supervisor refuses any non-KMS caller when the guard is enabled', async () => {
  const original = process.env.SUPERVISOR_NETWORK_GUARD;
  process.env.SUPERVISOR_NETWORK_GUARD = 'required';
  const lookup = async () => [{ address: '172.22.0.3' }];
  try {
    assert.equal(await peerAllowed({ url: '/snapshot', socket: { remoteAddress: '172.22.0.3' } }, lookup), true);
    assert.equal(await peerAllowed({ url: '/snapshot', socket: { remoteAddress: '172.22.0.7' } }, lookup), false);
    assert.equal(await peerAllowed({ url: '/metrics/history?limit=10',
      socket: { remoteAddress: '172.22.0.3' } }, lookup), true);
    assert.equal(await peerAllowed({ url: '/metrics/history',
      socket: { remoteAddress: '172.22.0.7' } }, lookup), false);
    assert.equal(await peerAllowed({ url: '/snapshot', socket: { remoteAddress: '127.0.0.1' } }, lookup), false);
    assert.equal(await peerAllowed({ url: '/snapshot', socket: { remoteAddress: '::ffff:172.22.0.3' } }, lookup), true);
    assert.equal(await peerAllowed({ url: '/health', socket: { remoteAddress: '127.0.0.1' } }, lookup), true);
    assert.equal(await peerAllowed({ url: '/health', socket: { remoteAddress: '172.22.0.3' } }, lookup), false);
    assert.equal(await peerAllowed({ url: '/metrics', socket: { remoteAddress: '172.22.0.3' } }, lookup), false);
  } finally {
    if (original === undefined) delete process.env.SUPERVISOR_NETWORK_GUARD;
    else process.env.SUPERVISOR_NETWORK_GUARD = original;
  }
});
test('Supervisor fails closed when Docker DNS is unavailable', async () => {
  const original = process.env.SUPERVISOR_NETWORK_GUARD;
  process.env.SUPERVISOR_NETWORK_GUARD = 'required';
  try {
    assert.equal(await peerAllowed({ url: '/snapshot', socket: { remoteAddress: '172.22.0.3' } },
      async () => { throw Error('Internal DNS unavailable'); }), false);
  } finally {
    if (original === undefined) delete process.env.SUPERVISOR_NETWORK_GUARD;
    else process.env.SUPERVISOR_NETWORK_GUARD = original;
  }
});
