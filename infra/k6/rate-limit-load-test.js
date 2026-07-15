// §12: "rate limiting verified under load (simple k6 script)."
//
// Targets GET /v1/documents rather than POST /v1/query — it exercises
// the exact same auth + rate-limit middleware
// (apps/api/src/kanuni_api/middleware/{auth,rate_limit}.py) without
// spending Groq credits or depending on a populated corpus / embedding
// models being loaded, which is all this script needs to verify.
//
// Usage:
//   k6 run -e BASE_URL=https://kanuni-api-staging.fly.dev \
//          -e API_KEY=<a query-scoped key> \
//          infra/k6/rate-limit-load-test.js
//
// A single API key has a configured `rate_limit_per_min` (60 by default
// — see infra/migrations for the api_keys table default). This script
// deliberately sends more than that from one VU so the limiter's 429s
// are expected, asserted-for behavior, not a failure: the real pass/fail
// question is "does excess load get a clean 429, or a 500 / hang?"

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_KEY = __ENV.API_KEY;

const rateLimited = new Counter('rate_limited_responses');
const serverErrors = new Counter('server_error_responses');
const cleanResponseRate = new Rate('clean_response_rate');

export const options = {
  scenarios: {
    burst_from_one_key: {
      executor: 'constant-vus',
      vus: 10,
      duration: '30s',
    },
  },
  thresholds: {
    // The real correctness bar: every response must be a clean 200 or
    // 429 — never a 500, timeout, or connection error — regardless of
    // how far over the limit this test pushes.
    clean_response_rate: ['rate>0.99'],
    // With 10 VUs hammering one key for 30s against a 60/min limit, the
    // limiter should actually engage at least once — if it never does,
    // this test isn't exercising what it claims to.
    rate_limited_responses: ['count>0'],
  },
};

export default function () {
  if (!API_KEY) {
    throw new Error('API_KEY env var is required — see this file\'s header comment.');
  }

  const response = http.get(`${BASE_URL}/v1/documents?limit=1`, {
    headers: { 'X-API-Key': API_KEY },
  });

  const isCleanResponse = response.status === 200 || response.status === 429;
  cleanResponseRate.add(isCleanResponse);

  if (response.status === 429) {
    rateLimited.add(1);
  } else if (response.status >= 500) {
    serverErrors.add(1);
  }

  check(response, {
    'status is 200 or 429 (never 5xx or a network error)': () => isCleanResponse,
    '429 responses carry an RFC 7807 body': (r) =>
      r.status !== 429 || (r.json() && r.json().error_code === 'rate_limit_exceeded'),
  });

  sleep(0.1);
}
