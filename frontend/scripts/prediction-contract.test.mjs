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

test('synthetic evaluation summary is fetched strictly and propagates backend errors', async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = '';
  const summary = {
    evaluation_type: 'deterministic_synthetic_simulation',
    simulated: true,
    real_operational_performance_claimed: false,
    scenario_count: 300,
    policies: { proposed: { mean_time_weighted_availability_pct: 60 } },
  };
  try {
    globalThis.fetch = async url => {
      requestedUrl = String(url);
      return { ok: true, status: 200, json: async () => summary };
    };
    const actual = await api.getEvaluationSummary();
    assert.equal(requestedUrl, '/api/evaluation/summary');
    assert.equal(actual.simulated, true);
    assert.equal(actual.real_operational_performance_claimed, false);
    assert.equal(actual.policies.proposed.mean_time_weighted_availability_pct, 60);

    globalThis.fetch = async () => ({
      ok: false,
      status: 503,
      json: async () => ({ detail: 'Evaluation unavailable' }),
    });
    await assert.rejects(api.getEvaluationSummary(), error => error.status === 503);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('risk-band policy uses the backend contract and propagates unavailable status', async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = '';
  const policy = {
    policy_id: 'demo-risk-bands-v1',
    configuration_source: 'built_in_default',
    configurable: true,
    health_score: { thresholds: [{ risk_level: 'CRITICAL', operator: '<', value: 45 }] },
    fd001: { health_score_formula: 'round(100 * min(RUL, 125) / 125)', rul_cap_cycles: 125, probability_status: 'unavailable', probability_calibrated: false },
  };
  try {
    globalThis.fetch = async url => {
      requestedUrl = String(url);
      return { ok: true, status: 200, json: async () => policy };
    };
    const actual = await api.getRiskBands();
    assert.equal(requestedUrl, '/api/policy/risk-bands');
    assert.equal(actual.health_score.thresholds[0].value, 45);
    assert.equal(actual.fd001.rul_cap_cycles, 125);
    assert.equal(actual.fd001.probability_calibrated, false);

    globalThis.fetch = async () => ({
      ok: false,
      status: 503,
      json: async () => ({ detail: 'Risk policy unavailable' }),
    });
    await assert.rejects(api.getRiskBands(), error => error.status === 503);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('saved FD001 artifact metrics use the read-only selected-model contract and propagate unavailable status', async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = '';
  const report = {
    status: 'available',
    source: 'existing_artifact_reference',
    evaluation_type: 'offline_simulation',
    dataset: 'NASA C-MAPSS FD001',
    unit: 'cycles',
    model: { version: 'cmapss-fd001-rf-v1', artifact_sha256: 'a'.repeat(64) },
    official_test: {
      engine_count: 100,
      protocol: 'one prediction per test engine at final observed cycle',
      metrics: { mae_cycles: 12.3, rmse_cycles: 18.4, nasa_asymmetric_score: 350.2 },
      uncertainty: {
        raw_tree_p10_p90: { observed_coverage: 0.7, nominal_coverage: 0.8, calibrated: false },
        mean_inclusive_envelope: { observed_coverage: 0.7, nominal_coverage: null, calibrated: false },
      },
    },
    scope: { dataset_source_note: 'Official test labels used for scoring only.' },
  };
  try {
    globalThis.fetch = async url => {
      requestedUrl = String(url);
      return { ok: true, status: 200, json: async () => report };
    };
    const actual = await api.getFd001Metrics();
    assert.equal(requestedUrl, '/api/ml/fd001/metrics');
    assert.equal(actual.model.version, 'cmapss-fd001-rf-v1');
    assert.equal(actual.official_test.uncertainty.raw_tree_p10_p90.observed_coverage, 0.7);
    assert.equal(actual.official_test.uncertainty.mean_inclusive_envelope.nominal_coverage, null);

    globalThis.fetch = async () => ({
      ok: false,
      status: 503,
      json: async () => ({ detail: 'FD001 metrics unavailable', metrics_status: 'unavailable' }),
    });
    await assert.rejects(api.getFd001Metrics(), error => error.status === 503);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
