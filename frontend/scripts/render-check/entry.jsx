// Renders every registered view through React's real render path and reports
// any that throw. This is the check that catches render-body bugs that
// `vite build` and module transform both miss (e.g. an undefined lookup).
//
// Run: npm run verify:views
import React from 'react';
import { renderToString } from 'react-dom/server';

// Resolved through the alias to the hooks stub, so this is the SAME module
// instance the views import.
import { preloadRecs, preloadDemand } from '../../src/services/hooks.js';

import FleetView from '../../src/pages/views/FleetView.jsx';
import BasesView from '../../src/pages/views/BasesView.jsx';
import AircraftView from '../../src/pages/views/AircraftView.jsx';
import MaintenanceView from '../../src/pages/views/MaintenanceView.jsx';
import ResourcesView from '../../src/pages/views/ResourcesView.jsx';
import RecommendationsView from '../../src/pages/views/RecommendationsView.jsx';
import MyBaseView from '../../src/pages/views/MyBaseView.jsx';
import BaseAircraftView from '../../src/pages/views/BaseAircraftView.jsx';
import BaseMaintenanceView from '../../src/pages/views/BaseMaintenanceView.jsx';
import BaseResourcesView from '../../src/pages/views/BaseResourcesView.jsx';
import InventoryView from '../../src/pages/views/InventoryView.jsx';
import { ArrivalConstraintNotice } from '../../src/pages/views/InventoryView.jsx';
import { RulEnvelope, RulHistoryChart, TopSensorDrivers } from '../../src/components/PredictionEvidence.jsx';
import ComponentsView from '../../src/pages/views/ComponentsView.jsx';
import TransfersView from '../../src/pages/views/TransfersView.jsx';
import MaintenanceResourcesView from '../../src/pages/views/MaintenanceResourcesView.jsx';
import LogisticsBasesView from '../../src/pages/views/LogisticsBasesView.jsx';
import Commander from '../../src/pages/Commander.jsx';
import { BaseMissionReadiness, MissionReadinessBand } from '../../src/pages/Commander.jsx';
import ResourceForecastPanel, { DemandStockChart, ForecastEligibilityNotice, SuggestedMoveRow } from '../../src/components/ResourceForecastPanel.jsx';
import { EvaluationHeadline, EvaluationIntervalChart, EvaluationResults, pairedSharingEffect } from '../../src/components/EvaluationSummaryPanel.jsx';
import BaseManager from '../../src/pages/BaseManager.jsx';
import Logistics from '../../src/pages/Logistics.jsx';
import { compareTimeWeightedAvailability } from '../../src/components/ReadinessSimulationPanel.jsx';
import { RiskPolicyDetails } from '../../src/components/RiskPolicyNote.jsx';

const noop = () => {};
const props = { onOpenAircraft: noop, refresh: noop, refreshKey: 0 };

await preloadRecs(['A17', 'A21', 'A24', 'A28', 'A35']);
await preloadDemand();
await preloadDemand('alpha');

const comparisonSnapshot = values => ({
  policies: Object.fromEntries(['no_action', 'nearest_feasible', 'proposed'].map((key, index) => [
    key, { metrics: { time_weighted_average_availability_pct: values[index] } },
  ])),
});
const comparisonChecks = [
  ['equal numeric values', [60, 60, 60], 'tie'],
  ['different numeric values', [60, 60, 65], 'different'],
  ['zero-horizon unavailable values', [null, null, null], 'unavailable'],
  ['partially unavailable values', [60, null, 60], 'unavailable'],
];
for (const [name, values, expected] of comparisonChecks) {
  const actual = compareTimeWeightedAvailability(comparisonSnapshot(values));
  if (actual !== expected) throw new Error(`Readiness comparison ${name}: expected ${expected}, got ${actual}`);
}
console.log(`  PASS  readiness comparison classification (${comparisonChecks.length} cases)`);

const arrivalNoticeChecks = [
  ['blocked arrival', { can_start_on_arrival: false, arrival_block_reason: 'DESTINATION_CONDITION_BELOW_MINIMUM' }, /Arrival does not make this work order startable under current constraints: Destination Condition Below Minimum/],
  ['startable arrival', { can_start_on_arrival: true, arrival_block_reason: null }, null],
  ['unknown arrival', { can_start_on_arrival: null, arrival_block_reason: 'NO_TRANSFERABLE_DESTINATION_STOCK' }, null],
];
for (const [name, row, expected] of arrivalNoticeChecks) {
  const html = renderToString(React.createElement(ArrivalConstraintNotice, { row }));
  const text = html.replace(/<!--.*?-->/g, '').replace(/<[^>]*>/g, '');
  if (expected ? !expected.test(text) : html !== '') {
    throw new Error(`Arrival constraint notice ${name}: unexpected rendered output ${html}`);
  }
}
console.log(`  PASS  arrival constraint notice rendering (${arrivalNoticeChecks.length} cases)`);

const rulChartHtml = renderToString(React.createElement(RulHistoryChart, {
  trend: [
    { cycle: 1, rul_cycles: 100, rul_low: 92, rul_high: 108 },
    { cycle: 25, rul_cycles: 52.29, rul_low: 45, rul_high: 61 },
  ],
}));
if (!rulChartHtml.includes('RUL history (cycles)')
  || !rulChartHtml.includes('tree-spread envelope, uncalibrated')
  || !rulChartHtml.includes('fill="#4f9cf0"')
  || !rulChartHtml.includes('not a confidence interval')) {
  throw new Error('RUL history chart should show its uncalibrated mean-inclusive tree-spread envelope');
}
const mockRulChartHtml = renderToString(React.createElement(RulHistoryChart, { trend: [] }));
const noIntervalRulChartHtml = renderToString(React.createElement(RulHistoryChart, {
  trend: [{ cycle: 25, rul_cycles: 52.29, rul_low: null, rul_high: null }],
}));
if (!mockRulChartHtml.includes('RUL history unavailable for this provider.')
  || mockRulChartHtml.includes('<svg')
  || !noIntervalRulChartHtml.includes('interval unavailable')
  || noIntervalRulChartHtml.includes('fill="#4f9cf0"')
  || !noIntervalRulChartHtml.includes('52.29')) {
  throw new Error('RUL history chart should preserve point values and represent unavailable bounds without a band');
}
const zeroRulEnvelopeHtml = renderToString(React.createElement(RulEnvelope, {
  prediction: { rul_low: 0, rul_high: 0.23, rul_unit: 'cycles' },
}));
const nullRulEnvelopeHtml = renderToString(React.createElement(RulEnvelope, {
  prediction: { rul_low: null, rul_high: null, rul_unit: 'cycles' },
}));
if (!zeroRulEnvelopeHtml.includes('0 cycles – 0.23 cycles')
  || !nullRulEnvelopeHtml.includes('Unavailable')) {
  throw new Error('Selected prediction envelope should preserve a real zero and represent null bounds as unavailable');
}
const driverFixture = Array.from({ length: 6 }, (_, index) => ({
  feature: `sensor_${index + 1}_mean`,
  sensor: `sensor_${index + 1}`,
  statistic: 'mean',
  contribution_score: index === 0 ? -0.42 : 0.1,
  direction: index === 0 ? 'below_reference' : 'above_reference',
}));
const driverHtml = renderToString(React.createElement(TopSensorDrivers, {
  drivers: driverFixture,
  method: 'importance_weighted_standardized_deviation_from_training_healthy_reference',
}));
const emptyDriverHtml = renderToString(React.createElement(TopSensorDrivers, { drivers: [], method: null }));
if ((driverHtml.match(/<b>/g) || []).length !== 5
  || !driverHtml.includes("capped high-RUL training-prefix reference")
  || !driverHtml.includes('not causal attribution or failure probability')
  || !driverHtml.includes('-0.420')
  || !emptyDriverHtml.includes('Sensor drivers unavailable for this provider.')) {
  throw new Error('Top sensor drivers should be bounded, signed, reference-labelled, and unavailable when absent');
}
console.log('  PASS  FD001 RUL envelope and sensor driver evidence rendering (populated, null, and zero cases)');

const riskPolicyHtml = renderToString(React.createElement(RiskPolicyDetails, { policy: {
  policy_id: 'demo-risk-bands-v1',
  source: 'backend.risk_band',
  configuration_source: 'DEMO_RISK_HEALTH_THRESHOLDS',
  configurable: true,
  health_score: { unit: 'score_0_to_100', thresholds: [
    { risk_level: 'CRITICAL', operator: '<', value: 45 },
    { risk_level: 'HIGH', operator: '<', value: 60 },
    { risk_level: 'MEDIUM', operator: '<', value: 80 },
    { risk_level: 'LOW', operator: '>=', value: 80 },
  ] },
  combination: { rule: 'most_severe' },
  fd001: { rul_unit: 'cycles', health_score_formula: 'round(100 * min(RUL, 125) / 125)', rul_cap_cycles: 125, probability_status: 'unavailable', probability_calibrated: false },
} }));
const missingRiskPolicyHtml = renderToString(React.createElement(RiskPolicyDetails, { policy: null }));
const riskPolicyText = riskPolicyHtml.replace(/<!--.*?-->/g, '');
if (!riskPolicyText.includes('round(100 * min(RUL, 125) / 125)')
  || !riskPolicyText.includes('RUL cap 125 cycles')
  || !riskPolicyText.includes('CRITICAL &lt; 45')
  || !riskPolicyText.includes('LOW &gt;= 80')
  || !riskPolicyText.includes('DEMO_RISK_HEALTH_THRESHOLDS')
  || !riskPolicyText.includes('not a calibrated failure probability')
  || !missingRiskPolicyHtml.includes('Health-score threshold values unavailable')
  || missingRiskPolicyHtml.includes('CRITICAL') || missingRiskPolicyHtml.includes('45')) {
  throw new Error('Risk policy note should render backend formula/thresholds and withhold fallback values when metadata is absent');
}
console.log('  PASS  backend-sourced risk policy rendering and unavailable metadata');

const readinessHtml = renderToString(React.createElement(MissionReadinessBand, {
  fleet: {
    mission_capable_rate_pct: 60,
    readiness_target_pct: 75,
    gap_to_target_pct: 15,
    nmcs_count: 2,
    aircraft_down_for_maintenance: 1,
  },
}));
const readinessMissingHtml = renderToString(React.createElement(MissionReadinessBand, {
  fleet: { mission_capable_rate_pct: null, readiness_target_pct: null, gap_to_target_pct: null, nmcs_count: null, aircraft_down_for_maintenance: null },
}));
const baseReadinessHtml = renderToString(React.createElement(BaseMissionReadiness, {
  base: { id: 'alpha', name: 'Base Alpha', mission_capable_rate_pct: 0, readiness_target_pct: 75, gap_to_target_pct: 75, nmcs_count: 0, aircraft_down_for_maintenance: 0 },
}));
const baseReadinessMissingHtml = renderToString(React.createElement(BaseMissionReadiness, {
  base: { id: 'bravo', mission_capable_rate_pct: null, readiness_target_pct: null, gap_to_target_pct: null, nmcs_count: null, aircraft_down_for_maintenance: null },
}));
const baseReadinessMetHtml = renderToString(React.createElement(BaseMissionReadiness, {
  base: { id: 'charlie', mission_capable_rate_pct: 75, readiness_target_pct: 75, gap_to_target_pct: 0, nmcs_count: 0, aircraft_down_for_maintenance: 0 },
}));
if (!readinessHtml.includes('60.0%') || !readinessHtml.includes('15.0 pp')
  || !readinessHtml.includes('NMCS proxy') || !readinessHtml.includes('Down for maintenance')
  || !readinessMissingHtml.includes('—') || readinessMissingHtml.includes('0.0%')
  || !baseReadinessHtml.includes('0.0%') || !baseReadinessHtml.includes('Target 75.0%')
  || !baseReadinessHtml.includes('fill="#e05c5c"') || !baseReadinessHtml.includes('color:#e05c5c')
  || !baseReadinessMetHtml.includes('fill="#3fb97f"')
  || !readinessHtml.includes('color:#d8a93d')
  || !baseReadinessMissingHtml.includes('color:#8b94a3')
  || !baseReadinessMissingHtml.includes('Gap unavailable') || !baseReadinessMissingHtml.includes('Target unavailable')
  || baseReadinessMissingHtml.includes('0.0%')) {
  throw new Error('Commander readiness displays should preserve backend metrics, target, real zero, and unavailable values');
}
console.log('  PASS  Commander fleet and base readiness metrics (populated, zero, and unavailable cases)');

const demandChartHtml = renderToString(React.createElement(DemandStockChart, {
  componentRow: { component: 'HP-204', committed_available_for_transfer: 2, expected_demand: 1.375 },
}));
const unavailableDemandChartHtml = renderToString(React.createElement(DemandStockChart, {
  componentRow: { component: 'HP-204', committed_available_for_transfer: 0, expected_demand: null },
}));
const demandChartText = html => html.replace(/<!--.*?-->/g, '');
if (!demandChartText(demandChartHtml).includes('Expected demand 1.38') || !demandChartText(demandChartHtml).includes('Uncommitted transferable stock 2')
  || !demandChartText(unavailableDemandChartHtml).includes('Expected demand Unavailable')
  || !demandChartText(unavailableDemandChartHtml).includes('Uncommitted transferable stock 0')) {
  throw new Error('Cycle demand chart should retain fractional expected demand, genuine zero stock, and unavailable demand');
}
console.log('  PASS  cycle resource stock-versus-demand chart (fractional and unavailable cases)');
const forecastEligibilityHtml = renderToString(React.createElement(ForecastEligibilityNotice, {
  forecast: { forecast_status: 'no_eligible_predictions', unavailable_prediction_count: 2, outside_horizon_prediction_count: 3, suggested_horizon_cycles: 60 },
  horizonCycles: 30,
}));
const forecastEligibilityText = forecastEligibilityHtml.replace(/<!--.*?-->/g, '').replace(/<[^>]*>/g, '');
if (!forecastEligibilityText.includes('No eligible cycle predictions overlap this horizon.')
  || !forecastEligibilityText.includes('2 predictions unavailable')
  || !forecastEligibilityText.includes('3 valid predictions fall outside the selected horizon')
  || !forecastEligibilityText.includes('Try 60 cycles; the backend found eligible predictions at that horizon.')) {
  throw new Error('Forecast eligibility notice should distinguish unavailable predictions from predictions outside the selected horizon');
}
const noSuggestionHtml = renderToString(React.createElement(ForecastEligibilityNotice, {
  forecast: { forecast_status: 'no_eligible_predictions', suggested_horizon_cycles: null },
  horizonCycles: 30,
}));
if (noSuggestionHtml.includes('Try ')) throw new Error('Forecast eligibility notice must not guess a horizon when the backend provides none');
const defaultForecastHtml = renderToString(React.createElement(ResourceForecastPanel, { canRequestMove: false }));
if (!defaultForecastHtml.includes('value="60"')
  || !defaultForecastHtml.includes('aria-label="Quick-select forecast horizon"')
  || !defaultForecastHtml.includes('aria-pressed="true"')) {
  throw new Error('Resource forecast panel should initially render its input and active quick-select at 60 cycles');
}
for (const cycle of [30, 60, 100]) {
  if (!defaultForecastHtml.includes(`aria-label="${cycle} cycles"`)) {
    throw new Error(`Forecast horizon quick-select should include ${cycle} cycles`);
  }
}
console.log('  PASS  forecast horizon default/quick-select and backend-suggested empty state');

const suggestedMove = { source_base: 'alpha', destination_base: 'bravo', quantity: 1, eta_hours: 4.3, distance_km: 260, condition_pct: 84, feasible: true };
const suggestedMoveRow = { base_id: 'bravo', component: 'HP-204' };
const logisticsMoveHtml = renderToString(React.createElement(SuggestedMoveRow, {
  move: suggestedMove, row: suggestedMoveRow, canRequestMove: true, onRequest: noop,
}));
const commanderMoveHtml = renderToString(React.createElement(SuggestedMoveRow, {
  move: suggestedMove, row: suggestedMoveRow, canRequestMove: false, onRequest: noop,
}));
const infeasibleMoveHtml = renderToString(React.createElement(SuggestedMoveRow, {
  move: { ...suggestedMove, feasible: false }, row: suggestedMoveRow, canRequestMove: true, onRequest: noop,
}));
const invalidQuantityMoveHtml = renderToString(React.createElement(SuggestedMoveRow, {
  move: { ...suggestedMove, quantity: 1.5 }, row: suggestedMoveRow, canRequestMove: true, onRequest: noop,
}));
if (!logisticsMoveHtml.includes('Base Alpha') || !logisticsMoveHtml.includes('Base Bravo')
  || !logisticsMoveHtml.includes('1 unit') || !logisticsMoveHtml.includes('4.3h')
  || !logisticsMoveHtml.includes('condition 84%') || !logisticsMoveHtml.includes('Create transfer')
  || /disabled(?:="")?/.test(logisticsMoveHtml)
  || !commanderMoveHtml.includes('Logistics role required') || !/disabled(?:="")?/.test(commanderMoveHtml)
  || !infeasibleMoveHtml.includes('not marked feasible') || !/disabled(?:="")?/.test(infeasibleMoveHtml)
  || !invalidQuantityMoveHtml.includes('quantity unavailable') || !/disabled(?:="")?/.test(invalidQuantityMoveHtml)) {
  throw new Error('Suggested transfers should show their backend route and only enable whole-unit feasible requests for Logistics');
}
console.log('  PASS  suggested transfer rendering and Logistics/feasibility action guards');

const evaluationFixture = {
  evaluation_type: 'deterministic_synthetic_simulation',
  simulated: true,
  real_operational_performance_claimed: false,
  scenario_count: 300,
  seed: 17,
  horizon_hours: 48,
  horizon_unit: 'hours',
  scenario_fingerprint: 'test-fingerprint',
  policies: {
    proposed: { label: 'Production ranking', mean_time_weighted_availability_pct: 0, availability_pct_ci95: { lower: 0, upper: 0 }, mean_available_aircraft_hours: 0, mean_summed_censored_aircraft_hours_lost: 0, median_summed_censored_aircraft_hours_lost: 0, summed_censored_aircraft_hours_lost_ci95: { lower: 0, upper: 0 }, mean_completed_work_orders: 0, mean_unserved_work_orders: 0, unserved_work_order_rate_pct: 0, unserved_rate_ci95: { lower: 0, upper: 0 } },
    nearest_fcfs: { label: 'Nearest feasible, first-come-first-served', mean_time_weighted_availability_pct: 60, availability_pct_ci95: { lower: 55, upper: 65 }, mean_available_aircraft_hours: 70, mean_summed_censored_aircraft_hours_lost: 20, median_summed_censored_aircraft_hours_lost: 18, summed_censored_aircraft_hours_lost_ci95: { lower: 16, upper: 24 }, mean_completed_work_orders: 2, mean_unserved_work_orders: 0, unserved_work_order_rate_pct: 0, unserved_rate_ci95: { lower: 0, upper: 0 } },
    random_feasible: { label: 'Random feasible source', mean_time_weighted_availability_pct: null, availability_pct_ci95: { lower: null, upper: null }, mean_available_aircraft_hours: null, mean_summed_censored_aircraft_hours_lost: null, median_summed_censored_aircraft_hours_lost: null, summed_censored_aircraft_hours_lost_ci95: { lower: null, upper: null }, mean_completed_work_orders: null, mean_unserved_work_orders: null, unserved_work_order_rate_pct: null, unserved_rate_ci95: { lower: null, upper: null } },
    local_only_procurement: { label: 'Local stock / procurement only', mean_time_weighted_availability_pct: 60, availability_pct_ci95: { lower: 55, upper: 65 }, mean_available_aircraft_hours: 70, mean_summed_censored_aircraft_hours_lost: 20, median_summed_censored_aircraft_hours_lost: 18, summed_censored_aircraft_hours_lost_ci95: { lower: 16, upper: 24 }, mean_completed_work_orders: 2, mean_unserved_work_orders: 0, unserved_work_order_rate_pct: 0, unserved_rate_ci95: { lower: 0, upper: 0 } },
  },
  comparison: {
    reference_policy: 'proposed',
    paired_deltas_vs_proposed: {
      nearest_fcfs: { time_weighted_availability_pct_points: { mean: 60, ci95: { lower: 55, upper: 65 } }, summed_censored_aircraft_hours_lost: { mean: 20, ci95: { lower: 16, upper: 24 } }, unserved_work_order_rate_pct_points: { mean: 0, ci95: { lower: 0, upper: 0 } } },
      random_feasible: {},
      local_only_procurement: { time_weighted_availability_pct_points: { mean: 60, ci95: { lower: 55, upper: 65 } }, summed_censored_aircraft_hours_lost: { mean: 20, ci95: { lower: 16, upper: 24 } }, unserved_work_order_rate_pct_points: { mean: 0, ci95: { lower: 0, upper: 0 } } },
    },
  },
  assumptions: ['Synthetic fixed-seed scenario fixture.'],
};
const evaluationHtml = renderToString(React.createElement(EvaluationResults, { summary: evaluationFixture }));
const unsafeEvaluationHtml = renderToString(React.createElement(EvaluationResults, { summary: { ...evaluationFixture, real_operational_performance_claimed: true } }));
const evaluationPolicyOrder = ['Production ranking', 'Nearest feasible, first-come-first-served', 'Random feasible source', 'Local stock / procurement only'];
const pairedHeadlineFixture = {
  ...evaluationFixture,
  // Deliberately conflicting marginal means: the headline must use paired deltas.
  policies: {
    ...evaluationFixture.policies,
    proposed: { ...evaluationFixture.policies.proposed, mean_time_weighted_availability_pct: 60 },
    local_only_procurement: { ...evaluationFixture.policies.local_only_procurement, mean_time_weighted_availability_pct: 60 },
  },
  comparison: {
    reference_policy: 'proposed',
    paired_deltas_vs_proposed: {
      local_only_procurement: {
        time_weighted_availability_pct_points: { mean: -4.5, ci95: { lower: -5.2, upper: -3.8 }, paired_sample_count: 300 },
        summed_censored_aircraft_hours_lost: { mean: 96, ci95: { lower: 90, upper: 102 }, paired_sample_count: 300 },
      },
      nearest_fcfs: {
        time_weighted_availability_pct_points: { mean: 0.01, ci95: { lower: -0.1, upper: 0.2 }, paired_sample_count: 300 },
        summed_censored_aircraft_hours_lost: { mean: 0.2, ci95: { lower: -1, upper: 1 }, paired_sample_count: 300 },
      },
    },
  },
};
const pairedHeadlineHtml = renderToString(React.createElement(EvaluationHeadline, { summary: pairedHeadlineFixture }));
const missingPairHeadlineHtml = renderToString(React.createElement(EvaluationHeadline, {
  summary: { comparison: { paired_deltas_vs_proposed: { nearest_fcfs: { time_weighted_availability_pct_points: { mean: 0, ci95: null } } } } },
}));
const nonzeroNearestHeadlineHtml = renderToString(React.createElement(EvaluationHeadline, {
  summary: { comparison: { paired_deltas_vs_proposed: { nearest_fcfs: {
    time_weighted_availability_pct_points: { mean: 1, ci95: { lower: 0.5, upper: 1.5 } },
    summed_censored_aircraft_hours_lost: { mean: 0, ci95: { lower: -1, upper: 1 } },
  } } } },
}));
const pairedEffect = pairedSharingEffect({ mean: 96, ci95: { lower: 90, upper: 102 } }, 24);
const unsupportedImprovementHtml = renderToString(React.createElement(EvaluationHeadline, {
  summary: { comparison: { paired_deltas_vs_proposed: {
    local_only_procurement: {
      time_weighted_availability_pct_points: { mean: -0.1, ci95: { lower: -0.5, upper: 0.2 } },
      summed_censored_aircraft_hours_lost: { mean: 96, ci95: { lower: 90, upper: 102 } },
    },
  } } },
}));
const invalidBoundsHeadlineHtml = renderToString(React.createElement(EvaluationHeadline, {
  summary: { comparison: { paired_deltas_vs_proposed: {
    local_only_procurement: {
      time_weighted_availability_pct_points: { mean: -1, ci95: { lower: 2, upper: 1 } },
      summed_censored_aircraft_hours_lost: { mean: 0, ci95: { lower: 2, upper: 1 } },
    },
  } } },
}));
if (pairedEffect?.mean !== -4 || pairedEffect.lower !== -4.25 || pairedEffect.upper !== -3.75
  || pairedSharingEffect({ mean: -1, ci95: { lower: 2, upper: 1 } }) !== null
  || !pairedHeadlineHtml.includes('+4.50 availability points (paired 95% CI +3.80 to +5.20)')
  || !pairedHeadlineHtml.includes('−4.00 aircraft-days lost per scenario (paired 95% CI −4.25 to −3.75)')
  || !pairedHeadlineHtml.includes('no distinguishable difference in these scenarios')
  || pairedHeadlineHtml.includes('−0.00 aircraft-days')
  || !missingPairHeadlineHtml.includes('no difference claim is made')
  || missingPairHeadlineHtml.includes('no distinguishable difference in these scenarios')
  || !nonzeroNearestHeadlineHtml.includes('at least one paired interval excludes zero')
  || !unsupportedImprovementHtml.includes('do not support a clear improvement')
  || unsupportedImprovementHtml.includes('paired intervals support improved modeled readiness')
  || !invalidBoundsHeadlineHtml.includes('no improvement claim is made')
  || !invalidBoundsHeadlineHtml.includes('Availability effect unavailable')) {
  throw new Error('Evaluation headline should derive sign and reversed CI bounds from paired deltas, guard missing intervals, and qualify nearest-policy claims');
}
console.log('  PASS  paired evaluation headline sign, CI order, null handling, and nearest-policy qualification');
if (!evaluationHtml.includes('SYNTHETIC SIMULATION')
  || !evaluationHtml.includes('95% percentile bootstrap intervals are over synthetic scenario units')
  || !evaluationHtml.includes('No policy is declared a winner')
  || !evaluationHtml.includes('>100</text>')
  || !evaluationHtml.includes('0.00 (0.00) · 0.00–0.00')
  || evaluationPolicyOrder.some((label, index) => evaluationHtml.indexOf(label) < 0 || (index > 0 && evaluationHtml.indexOf(label) < evaluationHtml.indexOf(evaluationPolicyOrder[index - 1])))
  || !evaluationHtml.includes('Nearest feasible, first-come-first-served</td><td>60.00 (55.00–65.00)')
  || !unsafeEvaluationHtml.includes('comparative metrics are withheld')
  || unsafeEvaluationHtml.includes('<svg')) {
  throw new Error('Evaluation card should show synthetic four-policy metrics and CIs in stable order, preserve zero/null, and withhold unconfirmed data');
}
console.log('  PASS  synthetic four-policy evaluation rendering (intervals, zero/null, order, and provenance guard)');

const CASES = [
  ['commander/dashboard', Commander, props],
  ['commander/fleet', FleetView, { ...props, focusBase: '' }],
  ['commander/fleet (base filter)', FleetView, { ...props, focusBase: 'bravo' }],
  ['commander/bases', BasesView, { ...props, onOpenBaseAircraft: noop }],
  ['commander/aircraft', AircraftView, props],
  ['commander/maintenance', MaintenanceView, props],
  ['commander/resources', ResourcesView, props],
  ['commander/recommendations', RecommendationsView, props],
  ['base/dashboard', BaseManager, { ...props, homeBase: 'alpha' }],
  ['base/mybase', MyBaseView, { ...props, homeBase: 'alpha' }],
  ['base/aircraft', BaseAircraftView, { ...props, homeBase: 'bravo' }],
  ['base/maintenance', BaseMaintenanceView, { ...props, homeBase: 'charlie' }],
  ['base/resources', BaseResourcesView, { ...props, homeBase: 'alpha' }],
  ['logistics/dashboard', Logistics, props],
  ['logistics/inventory', InventoryView, props],
  ['logistics/components', ComponentsView, props],
  ['logistics/transfers', TransfersView, props],
  ['logistics/mxresources', MaintenanceResourcesView, props],
  ['logistics/bases', LogisticsBasesView, props],
];

let failed = 0;
// A loading early-return is the shared Loading component rendered alone. Do
// not use output length: valid empty/error states can be short too.
function isLoadingEarlyReturn(html) {
  const text = html.replace(/<[^>]*>/g, '').trim();
  const onlyOneElement = (html.match(/<div\b/g) || []).length === 1
    && (html.match(/<\//g) || []).length === 1;
  return onlyOneElement && /^Loading [^…]+…$/.test(text);
}

function hasVisibleMarkupAndText(html) {
  const text = html.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim();
  return html.trim().startsWith('<') && text.length > 0;
}

for (const [name, View, p] of CASES) {
  try {
    const html = renderToString(React.createElement(View, p));
    if (!hasVisibleMarkupAndText(html)) {
      failed++;
      console.log(`  FAIL  ${name} — rendered no visible markup/text`);
    } else if (isLoadingEarlyReturn(html)) {
      failed++;
      console.log(`  STUCK ${name} — rendered only the loading early-return`);
    } else {
      console.log(`  PASS  ${name} (${html.length} chars)`);
    }
  } catch (e) {
    failed++;
    console.log(`  FAIL  ${name}\n        ${e.message}`);
  }
}

console.log(`\n${CASES.length - failed}/${CASES.length} views rendered`);
process.exitCode = failed ? 1 : 0;
await new Promise(r => setTimeout(r, 50));
