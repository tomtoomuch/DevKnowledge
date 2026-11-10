'use strict';

const http = require('node:http');
const { createSnapshotCollector } = require('./snapshot');
const { peerAllowed } = require('./peer-guard');
const { openMetricsStore, startMetricSampling, samplingInterval } = require('./metrics-store');

function createServer(collectSnapshot = createSnapshotCollector(), authorizePeer = peerAllowed,
                      metricsStore = null, authorizationHandler = null) {
  return http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    const parsed = new URL(req.url, 'http://localhost');
    const path = parsed.pathname;
    // The identity endpoint is only mounted if an authenticated session store
    // and a signing-key-backed handler are explicitly injected. Production's
    // current Collector startup does not mount it.
    if (path === '/internal/v1/sessions/authorize' && authorizationHandler) {
      return authorizationHandler(req, res);
    }
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

async function startSupervisor(config = process.env) {
  // A genuine identity authority is opt-in until Gateway/KMS have completed
  // their token-only integration. The default Collector behavior is preserved.
  const { startIdentityAuthority } = require('./identity-runtime');
  const { identityPeerAllowed } = require('./peer-guard');
  const mode = config.SUPERVISOR_IDENTITY_MODE || 'disabled';
  const MongoClient = mode === 'shadow' ? require('mongodb').MongoClient : null;
  const identity = await startIdentityAuthority({
    mode, config, MongoClient, peerGuard: identityPeerAllowed,
  });
  let metricsStore;
  let scheduler;
  try {
    const collect = createSnapshotCollector();
    metricsStore = openMetricsStore(config.METRICS_DB_PATH);
    scheduler = startMetricSampling(collect, metricsStore, {
      intervalMs: samplingInterval(config.METRICS_SAMPLE_INTERVAL_MS),
      retentionDays: 90,
      onFailure: (kind) => console.error('Supervisor metrics sampling failure (' + kind + ')'),
    });
    const server = createServer(collect, peerAllowed, metricsStore, identity.authorizationHandler);
    await new Promise((resolve, reject) => {
      server.once('error', reject);
      server.listen(9109, '0.0.0.0', resolve);
    });
    const stop = () => {
      scheduler.stop();
      server.close(async () => {
        try {
          metricsStore.close();
          await identity.close();
          process.exitCode = 0;
        } catch {
          process.exitCode = 1;
        }
      });
    };
    process.once('SIGINT', stop);
    process.once('SIGTERM', stop);
    return server;
  } catch (error) {
    scheduler?.stop();
    metricsStore?.close();
    await identity.close();
    throw error;
  }
}

if (require.main === module) {
  startSupervisor().catch(() => {
    // Never print connection strings, MongoDB credentials or token material.
    console.error('Supervisor startup failed');
    process.exitCode = 1;
  });
}

module.exports = { createServer, startSupervisor };
