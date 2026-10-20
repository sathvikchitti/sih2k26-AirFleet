import React from 'react';
import { api } from '../services/api.js';
import { ActionButton, Badge, DataError, SectionTitle } from './ui.jsx';
import { ChartTooltip, TipRow, useMeasuredWidth } from './charts.jsx';
import { C, CAT } from '../theme.js';

const POLICY_ORDER = ['proposed', 'nearest_fcfs', 'random_feasible', 'local_only_procurement'];
const POLICY_COLORS = CAT;
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
    <div style={{ border: `1px solid ${C.line2}`, borderRadius: 2, padding: '14px 16px', margin: '0 0 12px', background: C.deck }}>
      <div className="ops-card-title" style={{ marginBottom: 8 }}>
        Sharing spares across bases vs bases working alone
      </div>
      <div style={{ fontSize: 12, color: C.text }}>
        {availability
          ? `${signed(availability.mean)} availability points (paired 95% CI ${signed(availability.lower)} to ${signed(availability.upper)})`
          : 'Availability effect unavailable'}
        {'; '}
        {aircraftDays
          ? `${signed(aircraftDays.mean)} aircraft-days lost per scenario (paired 95% CI ${signed(aircraftDays.lower)} to ${signed(aircraftDays.upper)})`
          : 'Aircraft-days-lost effect unavailable'}.
      </div>
      {pairedCount != null ? <div style={{ fontSize: 10, color: C.muted, marginTop: 4 }}>Paired comparison across {pairedCount} synthetic scenarios; hours converted to 24-hour aircraft-days.</div> : null}
      <div style={{ fontSize: 11, color: C.text2, marginTop: 8 }}>
        <b>What this means:</b> {supportsImprovement
          ? 'In this synthetic benchmark, the paired intervals support improved modeled readiness and fewer aircraft-days lost when sharing is allowed versus local-only procurement.'
          : comparisonComplete
            ? 'The paired intervals do not support a clear improvement on both readiness and aircraft-days lost versus local-only procurement.'
            : 'The paired comparison is incomplete; no improvement claim is made versus local-only procurement.'}
        {' '}The result depends on the simulation’s stock, demand, and procurement assumptions. It does not establish that production ranking outperforms nearest-feasible selection; source condition, reserves, and donor impact remain ranking constraints.
      </div>
      <div role="status" style={{ fontSize: 11, color: C.muted, marginTop: 6 }}>
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
  const [frameRef, measured] = useMeasuredWidth(760);
  const width = Math.max(600, measured);
  const rowH = 30;
  const top = 30;
  const rowsAll = POLICY_ORDER.map((key, index) => ({ key, index, row: policies?.[key] || {} }));
  const height = top + rowsAll.length * rowH + 26;
  const labelW = Math.min(280, Math.round(width * 0.3));
  const rangeW = Math.round((width - labelW - 24 - 72) / 2);
  const availability = { start: labelW + 12, width: rangeW };
  const unserved = { start: labelW + 12 + rangeW + 72, width: rangeW };
  const [hover, setHover] = React.useState(null);
  const drawSeries = (row, y, name, range, color) => {
    const mean = name === 'availability'
      ? row.mean_time_weighted_availability_pct
      : row.unserved_work_order_rate_pct;
    const ci = name === 'availability' ? row.availability_pct_ci95 : row.unserved_rate_ci95;
    const meanX = scalePercent(mean, range.start, range.width);
    const lowX = scalePercent(ci?.lower, range.start, range.width);
    const highX = scalePercent(ci?.upper, range.start, range.width);
    if (meanX == null) return <text key={`${name}-na`} x={range.start} y={y + 4} fill={C.muted} fontSize="10">—</text>;
    return (
      <g key={name}>
        {lowX != null && highX != null ? <>
          <line x1={lowX} x2={highX} y1={y} y2={y} stroke={color} strokeWidth="2" strokeLinecap="round" />
          <line x1={lowX} x2={lowX} y1={y - 5} y2={y + 5} stroke={color} strokeWidth="2" strokeLinecap="round" />
          <line x1={highX} x2={highX} y1={y - 5} y2={y + 5} stroke={color} strokeWidth="2" strokeLinecap="round" />
        </> : null}
        <circle cx={meanX} cy={y} r="5" fill={color} stroke={C.deck} strokeWidth="2" />
      </g>
    );
  };
  const axis = (range, label, keyPrefix) => (
    <g>
      <text x={range.start} y="16" fill={C.text2} fontFamily="var(--font-mono)" fontSize="10" letterSpacing="0.06em">{label}</text>
      {[0, 25, 50, 75, 100].map(tick => <g key={`${keyPrefix}${tick}`}>
        <line x1={scalePercent(tick, range.start, range.width)} x2={scalePercent(tick, range.start, range.width)} y1={top - 6} y2={height - 22} stroke={C.line} strokeWidth="1" />
        <text x={scalePercent(tick, range.start, range.width)} y={height - 8} textAnchor="middle" fill={C.muted} fontFamily="var(--font-mono)" fontSize="9">{tick}</text>
      </g>)}
    </g>
  );
  const hoverRow = hover != null ? rowsAll[hover] : null;
  return (
    <div className="ops-chart-frame" ref={frameRef} style={{ overflowX: 'auto' }}>
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label="Four synthetic policy comparisons with mean availability and unserved work-order rates and bootstrap 95 percent intervals" className="ops-chart-svg ops-chart-well" style={{ minWidth: 600 }}>
        {rowsAll.map(({ key, index }) => {
          const y = top + index * rowH;
          return <rect key={`band-${key}`} x="0" y={y - rowH / 2 + 2} width={width} height={rowH - 4} fill={hover === index ? C.panel2 : index % 2 ? 'transparent' : C.panel} opacity={hover === index ? 1 : 0.6} />;
        })}
        {axis(availability, 'TIME-WEIGHTED AVAILABILITY %', 'a')}
        {axis(unserved, 'UNSERVED WORK-ORDER RATE %', 'u')}
        {rowsAll.map(({ key, index, row }) => {
          const y = top + index * rowH;
          const color = POLICY_COLORS[index];
          return <g key={key} onMouseEnter={() => setHover(index)} onMouseLeave={() => setHover(null)}>
            <rect x="0" y={y - rowH / 2} width={width} height={rowH} fill="transparent" />
            <rect x="10" y={y - 4} width="8" height="8" fill={color} />
            <text x="26" y={y + 4} fill={C.text} fontSize="11">{LABELS[key]}</text>
            {drawSeries(row, y, 'availability', availability, color)}
            {drawSeries(row, y, 'unserved', unserved, color)}
          </g>;
        })}
      </svg>
      {hoverRow && (
        <ChartTooltip xPct={48} yPct={((top + hoverRow.index * rowH) / height) * 100 + 6}>
          <div className="ops-chart-tip-title">{LABELS[hoverRow.key]}</div>
          <TipRow color={POLICY_COLORS[hoverRow.index]} label="Availability" value={`${fixed(hoverRow.row.mean_time_weighted_availability_pct)}% (${fixed(hoverRow.row.availability_pct_ci95?.lower)}–${fixed(hoverRow.row.availability_pct_ci95?.upper)})`} />
          <TipRow color={POLICY_COLORS[hoverRow.index]} label="Unserved rate" value={`${fixed(hoverRow.row.unserved_work_order_rate_pct)}% (${fixed(hoverRow.row.unserved_rate_ci95?.lower)}–${fixed(hoverRow.row.unserved_rate_ci95?.upper)})`} />
        </ChartTooltip>
      )}
    </div>
  );
}

export function EvaluationResults({ summary }) {
  const expectedType = summary?.evaluation_type === 'deterministic_synthetic_simulation'
    && summary?.simulated === true
    && summary?.real_operational_performance_claimed === false;
  if (!expectedType) {
    return <div role="alert" style={{ color: C.crit, fontSize: 12 }}>Evaluation payload does not confirm synthetic-only results; comparative metrics are withheld.</div>;
  }
  const policies = summary.policies || {};
  const comparisons = summary.comparison?.paired_deltas_vs_proposed || {};
  const alternatives = POLICY_ORDER.filter(key => key !== (summary.comparison?.reference_policy || 'proposed'));
  const assumptions = Array.isArray(summary.assumptions) ? summary.assumptions : [];
  return (
    <>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', fontSize: 11, color: C.muted, marginBottom: 10 }}>
        <Badge color={C.warn}>SYNTHETIC SIMULATION</Badge>
        <span>{summary.scenario_count ?? '—'} scenarios · seed {summary.seed ?? '—'}</span>
        <span>· {summary.horizon_hours ?? '—'} {summary.horizon_unit || 'hours'}</span>
        {summary.scenario_fingerprint ? <span title={summary.scenario_fingerprint}>· Snapshot {String(summary.scenario_fingerprint).slice(0, 12)}</span> : null}
      </div>
      <EvaluationHeadline summary={summary} />
      <div style={{ fontSize: 11, color: C.muted, marginBottom: 10 }}>
        Seeded scenario simulation only; results do not claim real operational performance. 95% percentile bootstrap intervals are over synthetic scenario units. No policy is declared a winner.
      </div>
      <EvaluationIntervalChart policies={policies} />
      <div style={{ overflowX: 'auto', marginTop: 10 }}>
        <table className="ops-table is-compact" style={{ minWidth: 870 }}>
          <thead><tr style={{ textAlign: 'left', color: C.muted, borderBottom: `1px solid ${C.line}` }}>
            <th>Policy</th><th>Mean availability · 95% CI</th><th>Mean available aircraft-hours</th><th>Summed censored aircraft-hours lost · mean (median), 95% CI</th><th>Mean completed WOs</th><th>Mean unserved WOs</th><th>Unserved rate · 95% CI</th>
          </tr></thead>
          <tbody>
            {POLICY_ORDER.map((key, index) => {
              const row = policies[key] || {};
              return <tr key={key} style={{ borderBottom: `1px solid ${C.line}` }}>
                <td style={{ fontWeight: 600, whiteSpace: 'nowrap' }}><span className="ops-swatch" style={{ background: POLICY_COLORS[index], marginRight: 8 }} />{row.label || LABELS[key]}</td>
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
      <div style={{ marginTop: 12, fontSize: 11, color: C.muted }}>
        Paired deltas versus {summary.comparison?.reference_policy || 'proposed'} (alternative minus reference):
        {alternatives.length ? <div style={{ overflowX: 'auto', marginTop: 5 }}>
          <table className="ops-table is-compact" style={{ minWidth: 690 }}>
            <thead><tr><th>Policy</th><th>Availability pp</th><th>Censored aircraft-hours lost</th><th>Unserved rate pp</th></tr></thead>
            <tbody>{alternatives.map(key => {
              const delta = comparisons[key] || {};
              return <tr key={key} style={{ borderTop: `1px solid ${C.line}` }}>
                <td style={{ whiteSpace: 'nowrap' }}><span className="ops-swatch" style={{ background: POLICY_COLORS[POLICY_ORDER.indexOf(key)], marginRight: 8 }} />{policies[key]?.label || LABELS[key]}</td>
                <td>{intervalText(delta.time_weighted_availability_pct_points?.mean, delta.time_weighted_availability_pct_points?.ci95)}</td>
                <td>{intervalText(delta.summed_censored_aircraft_hours_lost?.mean, delta.summed_censored_aircraft_hours_lost?.ci95)}</td>
                <td>{intervalText(delta.unserved_work_order_rate_pct_points?.mean, delta.unserved_work_order_rate_pct_points?.ci95)}</td>
              </tr>;
            })}</tbody>
          </table>
        </div> : <span> No paired comparisons available.</span>}
      </div>
      {assumptions.length ? <details style={{ marginTop: 10, fontSize: 11, color: C.muted }}>
        <summary style={{ cursor: 'pointer', color: C.warn }}>Simulation assumptions</summary>
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
        {loading && !summary ? <div role="status" style={{ color: C.muted, fontSize: 13 }}>Loading backend evaluation summary…</div> : null}
        {error ? <DataError error={error}>Evaluation summary unavailable. No fallback comparison is shown.</DataError> : null}
        {summary ? <EvaluationResults summary={summary} /> : null}
      </div>
    </section>
  );
}
