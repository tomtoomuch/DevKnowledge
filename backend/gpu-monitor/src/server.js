'use strict';

const http = require('node:http');
const { collectGpuMetrics } = require('./collector');

function createServer(collector = collectGpuMetrics) {
  return http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    if (req.method !== 'GET' || !['/health', '/metrics'].includes(req.url)) {
      res.writeHead(404).end(JSON.stringify({ detail: 'Not found' }));
      return;
    }
    if (req.url === '/health') {
      res.writeHead(200).end(JSON.stringify({ status: 'ok' }));
      return;
    }
    let snapshot;
    try { snapshot = await collector(); }
    catch { snapshot = { status: 'unavailable', devices: [] }; }
    res.writeHead(200).end(JSON.stringify(snapshot));
  });
}

if (require.main === module) {
  createServer().listen(9109, '0.0.0.0');
}

module.exports = { createServer };
