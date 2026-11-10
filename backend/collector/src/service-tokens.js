'use strict';

/**
 * ADR-004, transition-only internal token issuer.
 * The Supervisor must call this only after a verified session/RBAC lookup.
 * A token is SIGNED with HMAC-SHA-256, not encrypted.
 */
const { createHmac, randomBytes } = require('node:crypto');

const ISSUER = 'devknowledge-supervisor';
const AUDIENCE = 'api-kms';
const SCOPES = new Set([
  'knowledge.read', 'knowledge.create', 'knowledge.update', 'knowledge.delete',
]);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SECRET_FORMAT = /^[0-9a-f]{64}$/i;

function signingKey(secret) {
  if (typeof secret !== 'string' || !SECRET_FORMAT.test(secret)) {
    throw new Error('SUPERVISOR_KMS_TOKEN_KEY must be a 32-byte random hexadecimal secret');
  }
  return Buffer.from(secret, 'hex');
}

function encodeJson(value) {
  return Buffer.from(JSON.stringify(value), 'utf8').toString('base64url');
}

function issueKmsToken(principal, permission, secret, {
  nowSeconds = Math.floor(Date.now() / 1000),
  expiresInSeconds = 60,
  nonce = randomBytes(16).toString('hex'),
} = {}) {
  const key = signingKey(secret);
  if (!principal || typeof principal !== 'object' || !UUID.test(principal.user_id || '') ||
      !Array.isArray(principal.permissions) ||
      !SCOPES.has(permission) ||
      !principal.permissions.includes(permission)) {
    throw new Error('Verified identity and explicit knowledge permission required');
  }
  if (!Number.isSafeInteger(nowSeconds) || nowSeconds < 1 ||
      !Number.isSafeInteger(expiresInSeconds) || expiresInSeconds < 1 ||
      expiresInSeconds > 60 || !/^[0-9a-f]{32}$/.test(nonce)) {
    throw new Error('Invalid token lifetime or nonce');
  }
  const header = { alg: 'HS256', typ: 'JWT' };
  const claims = {
    iss: ISSUER,
    aud: AUDIENCE,
    sub: principal.user_id.toLowerCase(),
    scope: permission,
    iat: nowSeconds,
    exp: nowSeconds + expiresInSeconds,
    jti: nonce,
  };
  const unsigned = encodeJson(header) + '.' + encodeJson(claims);
  const signature = createHmac('sha256', key).update(unsigned, 'ascii').digest('base64url');
  return unsigned + '.' + signature;
}

module.exports = { signingKey, issueKmsToken, ISSUER, AUDIENCE };
