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
import ResourceForecastPanel, { DemandStockChart, ForecastEligibilityNotice } from '../../src/components/ResourceForecastPanel.jsx';
import { EvaluationIntervalChart, EvaluationResults } from '../../src/components/EvaluationSummaryPanel.jsx';
import BaseManager from '../../src/pages/BaseManager.jsx';
import Logistics from '../../src/pages/Logistics.jsx';
import { compareTimeWeightedAvailability } from '../../src/components/ReadinessSimulationPanel.jsx';

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
