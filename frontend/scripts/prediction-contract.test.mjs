import assert from 'node:assert/strict';
import test from 'node:test';

import {
  api,
  distanceBetween,
  distanceText,
  etaBetween,
  etaText,
  failureProbabilityText,
  healthScoreText,
  rulText,
} from '../src/services/api.js';

test('FD001 nullable prediction contract stays distinct from offline demo fallback', async () => {
  const originalFetch = globalThis.fetch;
  const prediction = {
    aircraft_id: 'A21',
    health_score: 42,
    health_score_derived: 'linear_rul_cap_125_cycles',
    failure_probability: null,
    probability_status: 'unavailable',
    rul: 52.287,
    rul_unit: 'cycles',
    prediction_horizon_hours: null,
    risk_level: 'CRITICAL',
    subsystem: null,
    predicted_maintenance: true,
    source: 'cmapss-fd001-demo-history',
    provider: 'fd001-random-forest',
    model_version: 'cmapss-fd001-rf-v1',
    history_source: 'synthetic_fd001_test_engine_history',
    is_synthetic: true,
  };

  try {
    globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => prediction });
    const actual = await api.getHealth('A21');

    assert.equal(actual.failure_probability, null);
    assert.equal(actual.probability_status, 'unavailable');
    assert.equal(Object.hasOwn(actual, 'confidence'), false);
    assert.equal(actual.subsystem, null);
    assert.equal(actual.rul_unit, 'cycles');
    assert.equal(actual.prediction_horizon_hours, null);
    assert.equal(actual.risk_level, 'CRITICAL');
    assert.equal(actual.source, 'cmapss-fd001-demo-history');
    assert.equal(actual.provider, 'fd001-random-forest');
    assert.equal(actual.model_version, 'cmapss-fd001-rf-v1');
    assert.equal(actual.history_source, 'synthetic_fd001_test_engine_history');
    assert.equal(actual.is_synthetic, true);
    assert.equal(failureProbabilityText(actual), 'Unavailable');
    assert.equal(failureProbabilityText({ failure_probability: actual.confidence }), 'Unavailable');
    assert.equal(healthScoreText(actual), '42%');
    assert.equal(rulText(actual), '52.29 cycles');
    assert.equal(healthScoreText({ health_score: 0 }), '0%');
    assert.equal(failureProbabilityText({ failure_probability: 0 }), '0%');
    assert.equal(rulText({ rul: 0, rul_unit: 'cycles' }), '0 cycles');
    assert.equal(distanceBetween('alpha', 'alpha'), 0);
    assert.equal(etaBetween('alpha', 'alpha'), 0);
    assert.equal(distanceText(null), '—');
    assert.equal(distanceText(0), '0 km');
    assert.equal(etaText(null), '—');
    assert.equal(etaText(0), '0h');
    assert.equal(api.isFallback(), false);

    // A provider/backend HTTP error is not silently replaced with demo health.
    globalThis.fetch = async () => ({
      ok: false,
      status: 503,
      json: async () => ({ detail: 'Selected prediction provider unavailable' }),
    });
    await assert.rejects(api.getHealth('A21'), error => error.status === 503);
    await assert.rejects(api.getFleet(), error => error.status === 503);
    assert.equal(api.isFallback(), false);

    // A genuine network-level outage may use bundled data, visibly marked as
    // synthetic illustrative demo fallback.
    globalThis.fetch = async () => { throw new TypeError('Failed to fetch'); };
    const fallback = await api.getHealth('A21');
    assert.equal(api.isFallback(), true);
    assert.equal(fallback.model_version, 'demo-fallback');
    assert.equal(fallback.is_synthetic, true);
    assert.equal(fallback.history_source, 'illustrative');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('cycle resource forecast preserves fractional demand and propagates provider errors', async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = '';
  const response = {
    forecast_status: 'available',
    horizon_cycles: 30,
    demand_method: 'indicative uncalibrated normal approximation',
    mutated_state: false,
    bases: [{ base_id: 'alpha', components: [{ component: 'HP-204', expected_demand: 1.375, projected_shortfall: 0 }] }],
  };
  try {
    globalThis.fetch = async url => {
      requestedUrl = String(url);
      return { ok: true, status: 200, json: async () => response };
    };
    const forecast = await api.getResourceForecast(30);
    assert.match(requestedUrl, /\/api\/resources\/forecast\?horizon_cycles=30$/);
    assert.equal(forecast.bases[0].components[0].expected_demand, 1.375);
    assert.equal(forecast.mutated_state, false);

    globalThis.fetch = async () => ({
      ok: false,
      status: 503,
      json: async () => ({ detail: 'Selected prediction provider unavailable' }),
    });
    await assert.rejects(api.getResourceForecast(30), error => error.status === 503);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
