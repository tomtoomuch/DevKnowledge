'use strict';

const { collectGpuMetrics } = require('./gpu');

const descriptions = Object.freeze({
  'api-gateway': ['API Gateway', "Point d'entrée HTTP unique"],
  'api-kms': ['Knowledge Service', 'API FastAPI et gestion des connaissances'],
  'mongodb': ['MongoDB', 'Base documentaire locale'],
  'collector': ['Collector', 'Collecte centralisée des sondes et du GPU'],
});

function service(id, status, detail) {
  const [name, description] = descriptions[id];
  return { id, name, description, status, detail };
}

function gatewayPort(value) {
  const port = Number(value);
  return Number.isInteger(port) && port >= 1 && port <= 65535 ? port : 3000;
}

// The fixed, uncredentialed endpoints cannot be replaced by client input.
// This service never has MongoDB credentials or a Docker socket.
async function probeJson(url, fetcher = fetch) {
  try {
    const response = await fetcher(url, {
      method: 'GET', signal: AbortSignal.timeout(2500),
      headers: { Accept: 'application/json' },
      redirect: 'manual',
    });
    const body = await response.text();
    if (body.length > 4096) return { status: 0, data: null };
    let data = null;
    try { data = JSON.parse(body); } catch { /* invalid probe data */ }
    return { status: response.status, data };
  } catch {
    return { status: 0, data: null };
  }
}

function validHealth(probe, name) {
  return probe.status === 200 && probe.data &&
    probe.data.status === 'ok' && probe.data.service === name;
}

function validReadiness(probe) {
  return probe.status === 200 && probe.data && probe.data.status === 'ok' &&
    probe.data.service === 'api-kms' && probe.data.dependency === 'mongodb';
}

function gpuTelemetry(result) {
  if (!result || result.status !== 'ok' || !Array.isArray(result.devices) || !result.devices.length) {
    return { status: 'unavailable', detail: 'Collecte GPU indisponible.', devices: [] };
  }
  return { status: 'healthy', detail: 'Mesures GPU disponibles.', devices: result.devices };
}

function createSnapshotCollector({
  probe = probeJson,
  gpu = collectGpuMetrics,
  gpuEnabled = () => process.env.GPU_MONITOR_ENABLED === 'true',
  port = () => gatewayPort(process.env.GATEWAY_PORT || '3000'),
} = {}) {
  return async function collectSnapshot() {
    const gateway = 'http://api-gateway:' + port();
    const kms = 'http://api-kms:8000';
    const [gatewayLive, kmsLive, kmsReady, gpuResult] = await Promise.all([
      probe(gateway + '/health'),
      probe(kms + '/health'),
      probe(kms + '/health/ready'),
      gpuEnabled() ? gpu().catch(() => ({ status: 'unavailable', devices: [] })) : Promise.resolve(null),
    ]);
    const gatewayOkay = validHealth(gatewayLive, 'api-gateway');
    const kmsOkay = validHealth(kmsLive, 'api-kms');
    const ready = validReadiness(kmsReady);
    const mongoUnavailable = kmsOkay && kmsReady.status === 503 &&
      kmsReady.data && kmsReady.data.service === 'api-kms' &&
      kmsReady.data.dependency === 'mongodb';

    return {
      checked_at: new Date().toISOString(),
      services: [
        service('api-gateway', gatewayOkay ? 'healthy' : 'unavailable',
          gatewayOkay ? 'La sonde HTTP de la Gateway répond.' : 'La Gateway ne répond pas à la sonde.'),
        service('api-kms', !kmsOkay ? 'unavailable' : ready ? 'healthy' : 'degraded',
          !kmsOkay ? 'Le KMS ne répond pas à la sonde.' :
            ready ? 'Le KMS répond et son stockage est disponible.' :
              'Le KMS répond mais la disponibilité du stockage est incertaine.'),
        service('mongodb', ready ? 'healthy' : mongoUnavailable ? 'unavailable' : 'unknown',
          ready ? 'Le ping MongoDB a réussi via la readiness du KMS.' :
            mongoUnavailable ? 'La readiness du KMS signale une panne MongoDB.' :
              'Aucune mesure MongoDB fiable n’est disponible.'),
        service('collector', 'healthy', 'Le service de collecte a produit cet instantané.'),
      ],
      gpu: gpuEnabled() ? gpuTelemetry(gpuResult) :
        { status: 'disabled', detail: 'Collecte GPU facultative non configurée.', devices: [] },
    };
  };
}

module.exports = { createSnapshotCollector, probeJson, gatewayPort, gpuTelemetry };
