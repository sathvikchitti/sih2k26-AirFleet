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
