// Carga sobre una bodega (a través de su LB). Variables:
//   BASE_URL      http://<ip-bodega>/api       (obligatoria)
//   PRODUCT_ID    producto a consultar (1)
//   VUS           usuarios concurrentes (100)
//   DURATION      duración (30s)
//   WRITE_RATIO   fracción de requests que registran un movimiento (0 = solo lectura)
//   SLEEP         pausa entre requests por usuario, en segundos (0)
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const BASE = __ENV.BASE_URL;
const PRODUCT = Number(__ENV.PRODUCT_ID || 1);
const WRITE_RATIO = Number(__ENV.WRITE_RATIO || 0);
const cacheHit = new Rate('cache_hit');

export const options = {
  vus: Number(__ENV.VUS || 100),
  duration: __ENV.DURATION || '30s',
  summaryTrendStats: ['avg', 'p(50)', 'p(95)', 'p(99)', 'max'],
  thresholds: { http_req_failed: ['rate<0.05'] },  // referencia, no corta la prueba
};

export function setup() {
  if (!BASE) throw new Error('Define BASE_URL, p. ej. http://1.2.3.4/api');
  const r = http.get(`${BASE}/inventory/${PRODUCT}`);
  if (r.status !== 200) throw new Error(`El producto ${PRODUCT} no existe en ${BASE}: ${r.status}`);
}

export default function () {
  const headers = { 'X-Correlation-ID': `COR-LOAD-${__VU}-${__ITER}` };
  if (Math.random() < WRITE_RATIO) {
    const r = http.post(`${BASE}/inventory/movements`,
      JSON.stringify({ product_id: PRODUCT, type: 'RECEIPT', quantity: 1, reference: 'k6' }),
      { headers: { ...headers, 'Content-Type': 'application/json' }, tags: { op: 'write' } });
    check(r, { 'write 201': (x) => x.status === 201 });
  } else {
    const r = http.get(`${BASE}/inventory/${PRODUCT}`, { headers, tags: { op: 'read' } });
    check(r, { 'read 200': (x) => x.status === 200 });
    cacheHit.add(r.headers['X-Cache'] === 'HIT');
  }
  if (__ENV.SLEEP) sleep(Number(__ENV.SLEEP));
}

export function handleSummary(data) {
  const m = data.metrics;
  const d = m.http_req_duration.values;
  const row = {
    label: __ENV.LABEL || 'run', vus: options.vus, duration: options.duration,
    requests: m.http_reqs.values.count, rps: +m.http_reqs.values.rate.toFixed(1),
    p50_ms: +d['p(50)'].toFixed(1), p95_ms: +d['p(95)'].toFixed(1), p99_ms: +d['p(99)'].toFixed(1),
    error_rate: +m.http_req_failed.values.rate.toFixed(4),
    cache_hit_rate: m.cache_hit ? +m.cache_hit.values.rate.toFixed(4) : null,
  };
  const out = { stdout: `\nRESULTADO ${JSON.stringify(row)}\n` };
  if (__ENV.OUT) out[__ENV.OUT] = JSON.stringify(row, null, 2);
  return out;
}
