"use strict";

// Temporary source-address allowlist on the internal Compose network.
// Not a cryptographic service identity: to be replaced by signed service credentials.
const dns = require("node:dns").promises;

function normalizeAddress(value) {
  return (value || "").startsWith("::ffff:") ? value.slice(7) : value;
}

async function peerAllowed(req, lookup = dns.lookup) {
  if (process.env.COLLECTOR_NETWORK_GUARD !== "required") return true;
  const peer = normalizeAddress(req.socket.remoteAddress);
  if (req.url === "/health") return peer === "127.0.0.1" || peer === "::1";
  const path = new URL(req.url, 'http://localhost').pathname;
  if (!["/snapshot", "/metrics/history"].includes(path)) return false;
  if (!peer || peer === "127.0.0.1" || peer === "::1") return false;
  try {
    const addresses = await lookup("api-kms", { family: 4, all: true });
    return Array.isArray(addresses) && addresses.some(x => x.address === peer);
  } catch {
    return false;
  }
}


async function identityPeerAllowed(req, lookup = dns.lookup) {
  if (process.env.COLLECTOR_NETWORK_GUARD !== "required") return true;
  const peer = normalizeAddress(req.socket.remoteAddress);
  if (!peer || peer === "127.0.0.1" || peer === "::1") return false;
  try {
    const addresses = await lookup("api-gateway", { family: 4, all: true });
    return Array.isArray(addresses) && addresses.some(item => item.address === peer);
  } catch {
    return false;
  }
}

module.exports = { peerAllowed, identityPeerAllowed, normalizeAddress };
