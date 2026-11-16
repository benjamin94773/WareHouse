// Fase 4: cada bodega con su propia carga (tasa constante de llegada).
//   WH1_URL, WH2_URL, WH3_URL = http://<ip>/api ; DURATION (60s)
// Por defecto WH-001 = 50 req/s, WH-002 = 800 req/s, WH-003 = 20 req/s (RATE_WH1/2/3 para cambiarlas).
import http from 'k6/http';
import { check } from 'k6';

const D = __ENV.DURATION || '60s';
const scenario = (rate, url) => ({
  executor: 'constant-arrival-rate', rate: Number(rate), timeUnit: '1s', duration: D,
  preAllocatedVUs: Math.max(10, Math.ceil(rate / 4)), maxVUs: Math.max(50, rate),
  exec: 'read', env: { URL: url },
});

export const options = {
  scenarios: {
    wh001: scenario(__ENV.RATE_WH1 || 50, __ENV.WH1_URL),
    wh002: scenario(__ENV.RATE_WH2 || 800, __ENV.WH2_URL),
    wh003: scenario(__ENV.RATE_WH3 || 20, __ENV.WH3_URL),
  },
  summaryTrendStats: ['avg', 'p(50)', 'p(95)', 'p(99)'],
  // Submétricas por bodega en el resumen
  thresholds: {
    'http_req_duration{scenario:wh001}': ['p(95)>=0'],
    'http_req_duration{scenario:wh002}': ['p(95)>=0'],
    'http_req_duration{scenario:wh003}': ['p(95)>=0'],
    'http_req_failed{scenario:wh001}': ['rate>=0'],
    'http_req_failed{scenario:wh002}': ['rate>=0'],
    'http_req_failed{scenario:wh003}': ['rate>=0'],
  },
};

export function read() {
  const r = http.get(`${__ENV.URL}/inventory/${__ENV.PRODUCT_ID || 1}`);
  check(r, { '200': (x) => x.status === 200 });
}
