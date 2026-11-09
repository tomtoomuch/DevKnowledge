'use strict';

const { execFile } = require('node:child_process');
const { promisify } = require('node:util');

const run = promisify(execFile);
const QUERY = '--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu';
const FORMAT = '--format=csv,noheader,nounits';

// Parse quoted CSV fields (GPU names may contain commas); never execute shell input.
function fields(line) {
  const result = [];
  let value = '';
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const c = line[i];
    if (c === '"') {
      if (quoted && line[i + 1] === '"') { value += '"'; i += 1; }
      else quoted = !quoted;
    } else if (c === ',' && !quoted) {
      result.push(value.trim());
      value = '';
    } else value += c;
  }
  if (quoted) throw new Error('Invalid CSV');
  result.push(value.trim());
  return result;
}

function numeric(raw, min, max) {
  if (/^(N\/A|\[Not Supported\]|\[Not Available\])$/i.test(raw)) return null;
  const value = Number(raw);
  if (!Number.isFinite(value) || value < min || value > max || raw === '') throw new Error('Invalid GPU metric');
  return value;
}

function parseNvidiaSmi(stdout) {
  if (typeof stdout !== 'string' || !stdout.trim()) throw new Error('Empty GPU output');
  const lines = stdout.trim().split(/\r?\n/);
  if (lines.length > 16) throw new Error('Too many GPUs');
  const seen = new Set();
  const devices = lines.map(line => {
    const columns = fields(line);
    if (columns.length !== 6) throw new Error('Unexpected GPU data columns');
    const index = numeric(columns[0], 0, 128);
    if (!Number.isInteger(index) || seen.has(index)) throw new Error('Invalid GPU index');
    seen.add(index);
    const name = columns[1];
    if (!name || name.length > 120) throw new Error('Invalid GPU name');
    const utilization_pct = numeric(columns[2], 0, 100);
    const memory_used_mib = numeric(columns[3], 0, 1048576);
    const memory_total_mib = numeric(columns[4], 0, 1048576);
    const temperature_c = numeric(columns[5], -40, 150);
    if (memory_used_mib !== null && memory_total_mib !== null && memory_used_mib > memory_total_mib) {
      throw new Error('Invalid memory counters');
    }
    return { index, name, utilization_pct, memory_used_mib, memory_total_mib, temperature_c };
  });
  return devices;
}

async function collectGpuMetrics(runner = run) {
  try {
    const { stdout } = await runner('nvidia-smi', [QUERY, FORMAT], {
      timeout: 3000, maxBuffer: 64 * 1024, encoding: 'utf8', windowsHide: true,
    });
    return { status: 'ok', devices: parseNvidiaSmi(stdout) };
  } catch {
    // Never return driver stderr, command paths or host-specific diagnostic details.
    return { status: 'unavailable', devices: [] };
  }
}

module.exports = { collectGpuMetrics, parseNvidiaSmi, QUERY, FORMAT };
