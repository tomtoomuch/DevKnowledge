'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { issueKmsToken, signingKey } = require('../src/service-tokens');

const KEY = '0123456789abcdef'.repeat(4);
const SUBJECT = 'e627de24-880c-4a22-b18e-7884ee0396a3';
const VERIFIED = { user_id: SUBJECT, permissions: ['knowledge.read'] };
const FIXTURE = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJkZXZrbm93bGVkZ2Utc3VwZXJ2aXNvciIsImF1ZCI6ImFwaS1rbXMiLCJzdWIiOiJlNjI3ZGUyNC04ODBjLTRhMjItYjE4ZS03ODg0ZWUwMzk2YTMiLCJzY29wZSI6Imtub3dsZWRnZS5yZWFkIiwiaWF0IjoxNzk0MzAwMDAwLCJleHAiOjE3OTQzMDAwNjAsImp0aSI6ImFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhIn0.eqvXQ0NG2-vu7zYGcGCDYIfGlzFwBp9sZuDvQEmGs_w';

test('issues a deterministic standard HS256 JWT usable by the Python verifier', () => {
  const token = issueKmsToken(VERIFIED, 'knowledge.read', KEY, {
    nowSeconds: 1794300000, expiresInSeconds: 60, nonce: 'a'.repeat(32),
  });
  assert.equal(token, FIXTURE);
  const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString('utf8'));
  assert.deepEqual(Object.keys(payload), ['iss', 'aud', 'sub', 'scope', 'iat', 'exp', 'jti']);
  assert.equal(payload.scope, 'knowledge.read');
  assert.equal(payload.aud, 'api-kms');
  assert.equal(payload.exp - payload.iat, 60);
  assert.equal(payload.password_hash, undefined);
});

test('never issues a token for an unverified identity or escalated permission', () => {
  for (const invalid of [
    null,
    { user_id: SUBJECT, permissions: ['users.manage'] },
    { user_id: 'not-a-uuid', permissions: ['knowledge.read'] },
    { user_id: SUBJECT, permissions: 'knowledge.read' },
    { user_id: SUBJECT, permissions: [] },
  ]) {
    assert.throws(() => issueKmsToken(invalid, 'knowledge.read', KEY), Error);
  }
  assert.throws(() => issueKmsToken(VERIFIED, 'users.manage', KEY), Error);
  assert.throws(() => issueKmsToken(VERIFIED, 'knowledge.delete', KEY), Error);
});

test('requires 256-bit hex key, bounded expiry and cryptographically unpredictable jti', () => {
  for (const invalid of [undefined, '', 'a'.repeat(16), 'q'.repeat(64)]) {
    assert.throws(() => signingKey(invalid), Error);
  }
  assert.equal(signingKey(KEY).length, 32);
  assert.throws(() => issueKmsToken(VERIFIED, 'knowledge.read', KEY,
    { expiresInSeconds: 61 }), Error);
  assert.throws(() => issueKmsToken(VERIFIED, 'knowledge.read', KEY,
    { nowSeconds: 1, expiresInSeconds: 0 }), Error);
  const first = issueKmsToken(VERIFIED, 'knowledge.read', KEY);
  const second = issueKmsToken(VERIFIED, 'knowledge.read', KEY);
  assert.notEqual(first, second, 'JWT identifiers must not be predictable or reused');
  assert.equal(first.split('.').length, 3);
});
