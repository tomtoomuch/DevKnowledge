'use strict';

const http = require('node:http');
const { createSnapshotCollector } = require('./snapshot');
const { peerAllowed } = require('./peer-guard');
const { openMetricsStore, startMetricSampling, samplingInterval } = require('./metrics-store');

function createServer(collectSnapshot = createSnapshotCollector(), authorizePeer = peerAllowed,
                      metricsStore = null) {
  return http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    const parsed = new URL(req.url, 'http://localhost');
    const path = parsed.pathname;
    if (req.method !== 'GET' || !['/health', '/snapshot', '/metrics/history'].includes(path)) {
      res.writeHead(404).end(JSON.stringify({ detail: 'Not found' }));
      return;
    }
    if (!(await authorizePeer(req))) {
      res.writeHead(404).end(JSON.stringify({ detail: 'Not found' }));
      return;
    }
    if (path === '/health') {
      res.writeHead(200).end(JSON.stringify({ status: 'ok', service: 'collector' }));
      return;
    }
    try {
      if (path === '/metrics/history') {
        if (!metricsStore || [...parsed.searchParams.keys()].some(key => key !== 'limit') ||
            parsed.searchParams.getAll('limit').length > 1) {
          res.writeHead(404).end(JSON.stringify({ detail: 'Not found' }));
          return;
        }
        const raw = parsed.searchParams.get('limit');
        if (raw !== null && !/^(?:[1-9]|[1-9][0-9]|100)$/.test(raw)) {
          res.writeHead(422).end(JSON.stringify({ detail: 'Invalid limit' }));
          return;
        }
        res.writeHead(200).end(JSON.stringify({ items: metricsStore.recent(
          raw === null ? 20 : Number(raw)) }));
        return;
      }
      const snapshot = await collectSnapshot();
      res.writeHead(200).end(JSON.stringify(snapshot));
    } catch {
      // A collector failure must not expose hostnames or other internal details.
      res.writeHead(503).end(JSON.stringify({ detail: 'Monitoring collector unavailable' }));
    }
  });
}

if (require.main === module) {
  // A mounted named volume is required in Compose; failed SQLite startup is fatal.
  const collect = createSnapshotCollector();
  const metricsStore = openMetricsStore(process.env.METRICS_DB_PATH);
  const scheduler = startMetricSampling(collect, metricsStore, {
    intervalMs: samplingInterval(process.env.METRICS_SAMPLE_INTERVAL_MS),
    retentionDays: 90,
    onFailure: (kind) => console.error('Supervisor metrics sampling failure (' + kind + ')'),
  });
  const server = createServer(collect, peerAllowed, metricsStore);
  server.listen(9109, '0.0.0.0');
  const stop = () => {
    scheduler.stop();
    server.close(() => {
      metricsStore.close();
      process.exit(0);
    });
  };
  process.once('SIGINT', stop);
  process.once('SIGTERM', stop);
}

module.exports = { createServer };
