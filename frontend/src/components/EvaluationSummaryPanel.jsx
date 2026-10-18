import React from 'react';
import { api } from '../services/api.js';
import { ActionButton, Badge, DataError, SectionTitle } from './ui.jsx';

const POLICY_ORDER = ['proposed', 'nearest_fcfs', 'random_feasible', 'local_only_procurement'];
const POLICY_COLORS = ['#d8a93d', '#4f9cf0', '#a78bfa', '#3fb97f'];
const isNumber = value => typeof value === 'number' && Number.isFinite(value);
const fixed = (value, digits = 2) => isNumber(value) ? Number(value).toFixed(digits) : '—';
const intervalText = (mean, ci, digits = 2) => !isNumber(mean)
  ? '—'
  : ci && isNumber(ci.lower) && isNumber(ci.upper)
    ? `${fixed(mean, digits)} (${fixed(ci.lower, digits)}–${fixed(ci.upper, digits)})`
    : `${fixed(mean, digits)} (CI unavailable)`;
const signed = value => `${value > 0 ? '+' : value < 0 ? '−' : ''}${fixed(Math.abs(value))}`;

export function pairedSharingEffect(delta, divisor = 1) {
  const ci = delta?.ci95;
  if (!isNumber(delta?.mean) || !isNumber(ci?.lower) || !isNumber(ci?.upper)
    || ci.lower > ci.upper || !isNumber(divisor) || divisor <= 0) return null;
  return {
    mean: -delta.mean / divisor,
    lower: -ci.upper / divisor,
    upper: -ci.lower / divisor,
  };
}

const intervalIncludesZero = delta => isNumber(delta?.ci95?.lower)
  && isNumber(delta?.ci95?.upper)
  && delta.ci95.lower <= 0
  && delta.ci95.upper >= 0;

export function EvaluationHeadline({ summary }) {
  const comparison = summary?.comparison?.paired_deltas_vs_proposed || {};
  const sharing = comparison.local_only_procurement || {};
  const availability = pairedSharingEffect(sharing.time_weighted_availability_pct_points);
  const aircraftDays = pairedSharingEffect(sharing.summed_censored_aircraft_hours_lost, 24);
  const supportsImprovement = availability != null && aircraftDays != null
    && availability.lower > 0 && aircraftDays.upper < 0;
  const comparisonComplete = availability != null && aircraftDays != null;
  const nearest = comparison.nearest_fcfs || {};
  const nearestComparable = intervalIncludesZero(nearest.time_weighted_availability_pct_points)
    && intervalIncludesZero(nearest.summed_censored_aircraft_hours_lost);
  const nearestAvailable = isNumber(nearest.time_weighted_availability_pct_points?.mean)
    && isNumber(nearest.summed_censored_aircraft_hours_lost?.mean)
    && isNumber(nearest.time_weighted_availability_pct_points?.ci95?.lower)
    && isNumber(nearest.time_weighted_availability_pct_points?.ci95?.upper)
    && isNumber(nearest.summed_censored_aircraft_hours_lost?.ci95?.lower)
    && isNumber(nearest.summed_censored_aircraft_hours_lost?.ci95?.upper);
  const scenarioCount = [
    sharing.time_weighted_availability_pct_points?.paired_sample_count,
    sharing.summed_censored_aircraft_hours_lost?.paired_sample_count,
  ].filter(isNumber);
  const pairedCount = scenarioCount.length ? Math.min(...scenarioCount) : null;

  return (
    <div style={{ border: '1px solid #3a3020', borderRadius: 8, padding: 10, margin: '0 0 10px', background: '#11141a' }}>
      <div style={{ color: '#f0c35a', fontSize: 13, fontWeight: 800, marginBottom: 5 }}>
        Sharing spares across bases vs bases working alone
      </div>
      <div style={{ fontSize: 12, color: '#e6e9ee' }}>
        {availability
          ? `${signed(availability.mean)} availability points (paired 95% CI ${signed(availability.lower)} to ${signed(availability.upper)})`
          : 'Availability effect unavailable'}
        {'; '}
        {aircraftDays
          ? `${signed(aircraftDays.mean)} aircraft-days lost per scenario (paired 95% CI ${signed(aircraftDays.lower)} to ${signed(aircraftDays.upper)})`
          : 'Aircraft-days-lost effect unavailable'}.
      </div>
      {pairedCount != null ? <div style={{ fontSize: 10, color: '#8b94a3', marginTop: 4 }}>Paired comparison across {pairedCount} synthetic scenarios; hours converted to 24-hour aircraft-days.</div> : null}
      <div style={{ fontSize: 11, color: '#c6ccd6', marginTop: 8 }}>
        <b>What this means:</b> {supportsImprovement
          ? 'In this synthetic benchmark, the paired intervals support improved modeled readiness and fewer aircraft-days lost when sharing is allowed versus local-only procurement.'
          : comparisonComplete
            ? 'The paired intervals do not support a clear improvement on both readiness and aircraft-days lost versus local-only procurement.'
            : 'The paired comparison is incomplete; no improvement claim is made versus local-only procurement.'}
        {' '}The result depends on the simulation’s stock, demand, and procurement assumptions. It does not establish that production ranking outperforms nearest-feasible selection; source condition, reserves, and donor impact remain ranking constraints.
      </div>
      <div role="status" style={{ fontSize: 11, color: '#8b94a3', marginTop: 6 }}>
        {nearestComparable
          ? 'Production ranking vs nearest-feasible: no distinguishable difference in these scenarios; paired 95% intervals include zero for availability and aircraft-hours lost.'
          : nearestAvailable
            ? 'Production ranking vs nearest-feasible: at least one paired interval excludes zero; review the paired deltas below. No overall winner is declared.'
            : 'Production ranking vs nearest-feasible: paired comparison unavailable; no difference claim is made.'}
      </div>
    </div>
  );
}

const LABELS = {
  proposed: 'Production ranking',
  nearest_fcfs: 'Nearest feasible, first-come-first-served',
  random_feasible: 'Random feasible source',
  local_only_procurement: 'Local stock / procurement only',
};

function scalePercent(value, start, width) {
  if (!isNumber(value)) return null;
  return start + Math.max(0, Math.min(100, value)) / 100 * width;
}

export function EvaluationIntervalChart({ policies }) {
  const width = 760;
  const height = 146;
  const availability = { start: 190, width: 220 };
  const unserved = { start: 505, width: 220 };
  const rows = POLICY_ORDER.map((key, index) => ({ key, index, row: policies?.[key] || {} }));
  const drawSeries = (row, y, name, range, color) => {
    const mean = name === 'availability'
      ? row.mean_time_weighted_availability_pct
      : row.unserved_work_order_rate_pct;
    const ci = name === 'availability' ? row.availability_pct_ci95 : row.unserved_rate_ci95;
    const meanX = scalePercent(mean, range.start, range.width);
    const lowX = scalePercent(ci?.lower, range.start, range.width);
    const highX = scalePercent(ci?.upper, range.start, range.width);
    if (meanX == null) return <text key={`${name}-na`} x={range.start} y={y + 4} fill="#8b94a3" fontSize="10">—</text>;
    return (
      <g key={name}>
        {lowX != null && highX != null ? <>
          <line x1={lowX} x2={highX} y1={y} y2={y} stroke={color} strokeWidth="2" />
          <line x1={lowX} x2={lowX} y1={y - 4} y2={y + 4} stroke={color} strokeWidth="1.5" />
          <line x1={highX} x2={highX} y1={y - 4} y2={y + 4} stroke={color} strokeWidth="1.5" />
        </> : null}
        <circle cx={meanX} cy={y} r="3.5" fill={color} />
      </g>
    );
  };
  return (
    <div style={{ overflowX: 'auto' }}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Four synthetic policy comparisons with mean availability and unserved work-order rates and bootstrap 95 percent intervals" style={{ display: 'block', width: '100%', minWidth: 600, height: 145, background: '#0a0e13', border: '1px solid #2a3444', borderRadius: 8 }}>
        <text x={availability.start} y="14" fill="#c6ccd6" fontSize="10">Time-weighted availability · %</text>
        <text x={unserved.start} y="14" fill="#c6ccd6" fontSize="10">Unserved work-order rate · %</text>
        {[0, 50, 100].map(tick => <g key={`a${tick}`}>
          <line x1={scalePercent(tick, availability.start, availability.width)} x2={scalePercent(tick, availability.start, availability.width)} y1="20" y2="126" stroke="#2a3444" strokeWidth="1" />
          <text x={scalePercent(tick, availability.start, availability.width)} y="140" textAnchor="middle" fill="#8b94a3" fontSize="9">{tick}</text>
        </g>)}
        {[0, 50, 100].map(tick => <g key={`u${tick}`}>
          <line x1={scalePercent(tick, unserved.start, unserved.width)} x2={scalePercent(tick, unserved.start, unserved.width)} y1="20" y2="126" stroke="#2a3444" strokeWidth="1" />
          <text x={scalePercent(tick, unserved.start, unserved.width)} y="140" textAnchor="middle" fill="#8b94a3" fontSize="9">{tick}</text>
        </g>)}
        {rows.map(({ key, index, row }) => {
          const y = 34 + index * 25;
          const color = POLICY_COLORS[index];
          return <g key={key}>
            <text x="8" y={y + 4} fill={color} fontSize="10">{LABELS[key]}</text>
            {drawSeries(row, y, 'availability', availability, color)}
            {drawSeries(row, y, 'unserved', unserved, color)}
          </g>;
        })}
      </svg>
    </div>
  );
}

export function EvaluationResults({ summary }) {
  const expectedType = summary?.evaluation_type === 'deterministic_synthetic_simulation'
    && summary?.simulated === true
    && summary?.real_operational_performance_claimed === false;
  if (!expectedType) {
    return <div role="alert" style={{ color: '#e05c5c', fontSize: 12 }}>Evaluation payload does not confirm synthetic-only results; comparative metrics are withheld.</div>;
  }
  const policies = summary.policies || {};
  const comparisons = summary.comparison?.paired_deltas_vs_proposed || {};
  const alternatives = POLICY_ORDER.filter(key => key !== (summary.comparison?.reference_policy || 'proposed'));
  const assumptions = Array.isArray(summary.assumptions) ? summary.assumptions : [];
  return (
    <>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', fontSize: 11, color: '#8b94a3', marginBottom: 10 }}>
        <Badge color="#d8a93d">SYNTHETIC SIMULATION</Badge>
        <span>{summary.scenario_count ?? '—'} scenarios · seed {summary.seed ?? '—'}</span>
        <span>· {summary.horizon_hours ?? '—'} {summary.horizon_unit || 'hours'}</span>
        {summary.scenario_fingerprint ? <span title={summary.scenario_fingerprint}>· Snapshot {String(summary.scenario_fingerprint).slice(0, 12)}</span> : null}
      </div>
      <EvaluationHeadline summary={summary} />
      <div style={{ fontSize: 11, color: '#8b94a3', marginBottom: 10 }}>
        Seeded scenario simulation only; results do not claim real operational performance. 95% percentile bootstrap intervals are over synthetic scenario units. No policy is declared a winner.
      </div>
      <EvaluationIntervalChart policies={policies} />
      <div style={{ overflowX: 'auto', marginTop: 10 }}>
        <table style={{ width: '100%', minWidth: 870, fontSize: 11, borderCollapse: 'collapse' }}>
          <thead><tr style={{ textAlign: 'left', color: '#8b94a3', borderBottom: '1px solid #2a3444' }}>
            <th style={{ padding: 7 }}>Policy</th><th>Mean availability · 95% CI</th><th>Mean available aircraft-hours</th><th>Summed censored aircraft-hours lost · mean (median), 95% CI</th><th>Mean completed WOs</th><th>Mean unserved WOs</th><th>Unserved rate · 95% CI</th>
          </tr></thead>
          <tbody>
            {POLICY_ORDER.map((key, index) => {
              const row = policies[key] || {};
              return <tr key={key} style={{ borderBottom: '1px solid #2a3444' }}>
                <td style={{ padding: 7, color: POLICY_COLORS[index], fontWeight: 700 }}>{row.label || LABELS[key]}</td>
                <td>{intervalText(row.mean_time_weighted_availability_pct, row.availability_pct_ci95)}{isNumber(row.mean_time_weighted_availability_pct) ? '%' : ''}</td>
                <td>{fixed(row.mean_available_aircraft_hours)}</td>
                <td>{isNumber(row.mean_summed_censored_aircraft_hours_lost)
                  ? `${fixed(row.mean_summed_censored_aircraft_hours_lost)} (${fixed(row.median_summed_censored_aircraft_hours_lost)}) · ${row.summed_censored_aircraft_hours_lost_ci95 && isNumber(row.summed_censored_aircraft_hours_lost_ci95.lower) && isNumber(row.summed_censored_aircraft_hours_lost_ci95.upper) ? `${fixed(row.summed_censored_aircraft_hours_lost_ci95.lower)}–${fixed(row.summed_censored_aircraft_hours_lost_ci95.upper)}` : 'CI unavailable'}`
                  : '—'}</td>
                <td>{fixed(row.mean_completed_work_orders)}</td>
                <td>{fixed(row.mean_unserved_work_orders)}</td>
                <td>{intervalText(row.unserved_work_order_rate_pct, row.unserved_rate_ci95)}{isNumber(row.unserved_work_order_rate_pct) ? '%' : ''}</td>
              </tr>;
            })}
          </tbody>
        </table>
      </div>
      <div style={{ marginTop: 12, fontSize: 11, color: '#8b94a3' }}>
        Paired deltas versus {summary.comparison?.reference_policy || 'proposed'} (alternative minus reference):
        {alternatives.length ? <div style={{ overflowX: 'auto', marginTop: 5 }}>
          <table style={{ width: '100%', minWidth: 690, fontSize: 10, borderCollapse: 'collapse' }}>
            <thead><tr style={{ textAlign: 'left', color: '#8b94a3' }}><th style={{ padding: 5 }}>Policy</th><th>Availability pp</th><th>Censored aircraft-hours lost</th><th>Unserved rate pp</th></tr></thead>
            <tbody>{alternatives.map(key => {
              const delta = comparisons[key] || {};
              return <tr key={key} style={{ borderTop: '1px solid #2a3444' }}>
                <td style={{ padding: 5, color: POLICY_COLORS[POLICY_ORDER.indexOf(key)] }}>{policies[key]?.label || LABELS[key]}</td>
                <td>{intervalText(delta.time_weighted_availability_pct_points?.mean, delta.time_weighted_availability_pct_points?.ci95)}</td>
                <td>{intervalText(delta.summed_censored_aircraft_hours_lost?.mean, delta.summed_censored_aircraft_hours_lost?.ci95)}</td>
                <td>{intervalText(delta.unserved_work_order_rate_pct_points?.mean, delta.unserved_work_order_rate_pct_points?.ci95)}</td>
              </tr>;
            })}</tbody>
          </table>
        </div> : <span> No paired comparisons available.</span>}
      </div>
      {assumptions.length ? <details style={{ marginTop: 10, fontSize: 11, color: '#8b94a3' }}>
        <summary style={{ cursor: 'pointer', color: '#d8a93d' }}>Simulation assumptions</summary>
        <ul style={{ margin: '5px 0 0', paddingLeft: 18 }}>{assumptions.map((item, index) => <li key={index}>{item}</li>)}</ul>
      </details> : null}
    </>
  );
}

export default function EvaluationSummaryPanel({ refreshKey = 0 }) {
  const [summary, setSummary] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [attempt, setAttempt] = React.useState(0);
  React.useEffect(() => {
    let active = true;
    setSummary(null);
    setLoading(true);
    setError(null);
    api.getEvaluationSummary()
      .then(result => { if (active) setSummary(result); })
      .catch(err => { if (active) setError(err); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refreshKey, attempt]);

  return (
    <section style={{ margin: '18px 0' }} aria-label="Synthetic policy evaluation summary">
      <SectionTitle right={<ActionButton small disabled={loading} onClick={() => setAttempt(value => value + 1)}>{loading ? 'Loading…' : 'Refresh evaluation'}</ActionButton>}>
        Policy evaluation · synthetic scenarios
      </SectionTitle>
      <div className="ops-card" style={{ padding: 14 }}>
        {loading && !summary ? <div role="status" style={{ color: '#8b94a3', fontSize: 13 }}>Loading backend evaluation summary…</div> : null}
        {error ? <DataError error={error}>Evaluation summary unavailable. No fallback comparison is shown.</DataError> : null}
        {summary ? <EvaluationResults summary={summary} /> : null}
      </div>
    </section>
  );
}
