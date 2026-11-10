'use strict';

const http = require('node:http');
const { createSnapshotCollector } = require('./snapshot');
const { peerAllowed } = require('./peer-guard');

function createServer(collectSnapshot = createSnapshotCollector(), authorizePeer = peerAllowed) {
  return http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    if (req.method !== 'GET' || !['/health', '/snapshot'].includes(req.url)) {
      res.writeHead(404).end(JSON.stringify({ detail: 'Not found' }));
      return;
    }
    if (!(await authorizePeer(req))) {
      res.writeHead(404).end(JSON.stringify({ detail: 'Not found' }));
      return;
    }
    if (req.url === '/health') {
      res.writeHead(200).end(JSON.stringify({ status: 'ok', service: 'collector' }));
      return;
    }
    try {
      const snapshot = await collectSnapshot();
      res.writeHead(200).end(JSON.stringify(snapshot));
    } catch {
      // A collector failure must not expose hostnames or other internal details.
      res.writeHead(503).end(JSON.stringify({ detail: 'Monitoring collector unavailable' }));
    }
  });
}

if (require.main === module) {
  createServer().listen(9109, '0.0.0.0');
}

module.exports = { createServer };
