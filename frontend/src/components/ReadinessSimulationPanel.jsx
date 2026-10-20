import React from 'react';
import { api } from '../services/api.js';
import { ActionButton, Badge, DataError, SectionTitle } from './ui.jsx';
import { C, CAT } from '../theme.js';
import { AvailabilityCurveChart } from './charts.jsx';

const POLICIES = [
  ['no_action', 'No new allocations'],
  ['nearest_feasible', 'Nearest feasible'],
  ['proposed', 'Proposed ranking'],
];

const metric = (value, digits = 2) => value == null || !Number.isFinite(Number(value))
  ? '—' : Number(value).toFixed(digits);

export function compareTimeWeightedAvailability(simulation) {
  const values = POLICIES.map(([key]) => {
    const metrics = simulation?.policies?.[key]?.metrics || simulation?.policy_metrics?.[key];
    return metrics?.time_weighted_average_availability_pct;
  });
  if (!values.every(Number.isFinite)) return 'unavailable';
  return values.every(value => value === values[0]) ? 'tie' : 'different';
}

export default function ReadinessSimulationPanel({ refreshKey }) {
  const [horizonInput, setHorizonInput] = React.useState('48');
  const [simulation, setSimulation] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [requestKey, setRequestKey] = React.useState(0);

  React.useEffect(() => {
    let active = true;
    const horizon = Number(horizonInput);
    if (!Number.isFinite(horizon) || horizon < 0 || horizon > 168) {
      setError(new Error('Enter a horizon from 0 to 168 hours.'));
      setSimulation(null);
      setLoading(false);
      return () => { active = false; };
    }
    setLoading(true);
    setError(null);
    api.getReadinessSimulation(horizon)
      .then(data => { if (active) setSimulation(data); })
      .catch(err => { if (active) { setError(err); setSimulation(null); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refreshKey, requestKey, horizonInput]);

  const refresh = () => setRequestKey(key => key + 1);
  const policies = simulation?.policies || {};
  const comparison = simulation?.comparison || [];
  const points = [];
  POLICIES.forEach(([key]) => (policies[key]?.curve || []).forEach(point => {
    const started = point.started_work_order_ids || [];
    const completed = point.completed_work_order_ids || [];
    if (started.length || completed.length) points.push({ key, policy: policies[key]?.label || key, hours: point.hours, started, completed, available: point.available_aircraft, total: point.total_aircraft, pct: point.availability_pct });
  }));
  points.sort((a, b) => a.hours - b.hours || a.key.localeCompare(b.key));
  const completionSets = POLICIES.map(([key, label]) => `${label}: ${(policies[key]?.metrics?.work_orders_completed_by_horizon ?? '—')} work orders completed`).join(' · ');
  const availabilityComparison = simulation ? compareTimeWeightedAvailability(simulation) : null;

  return (
    <section style={{ marginTop: 20 }} aria-label="Read-only fleet readiness simulation">
      <SectionTitle>Readiness what-if · read-only estimate</SectionTitle>
      <div className="ops-card" style={{ padding: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
          <label htmlFor="readiness-horizon" style={{ color: C.muted, fontSize: 12 }}>Simulation horizon (hours)</label>
          <input id="readiness-horizon" type="number" min="0" max="168" step="1" value={horizonInput} onChange={event => setHorizonInput(event.target.value)} style={{ width: 90, background: C.deck, border: `1px solid ${C.line}`, borderRadius: 2, padding: '7px 9px', color: C.text }} />
          <ActionButton small disabled={loading} onClick={refresh}>{loading ? 'Simulating…' : 'Refresh snapshot'}</ActionButton>
          {simulation?.mutated_state === false && <Badge color={C.info}>NO STATE CHANGE</Badge>}
        </div>
        <div style={{ fontSize: 12, color: C.muted, marginBottom: 12 }}>
          Compares one frozen fleet/inventory/work-order/prediction snapshot. This estimate does not approve transfers, change stock, or make a flight-release decision.
        </div>
        {loading && !simulation ? <div style={{ color: C.muted, fontSize: 13 }}>Loading readiness estimate…</div> : null}
        {error ? <DataError error={error}>Readiness simulation unavailable.</DataError> : null}
        {simulation && (
          <>
            <div style={{ fontSize: 12, color: C.muted, marginBottom: 10 }}>
              Snapshot availability: <b style={{ color: C.text }}>{simulation.current_available_aircraft}/{simulation.total_aircraft} · {simulation.current_availability_pct}%</b>
              {' · '}{simulation.horizon_hours} {simulation.horizon_unit || 'hours'}
            </div>
            <div style={{ margin: '4px 0 18px' }}>
              <AvailabilityCurveChart
                horizon={simulation.horizon_hours}
                series={[['no_action', CAT[2]], ['nearest_feasible', CAT[1]], ['proposed', CAT[0]]].map(([key, color]) => ({
                  key, color,
                  label: policies[key]?.label || POLICIES.find(([k]) => k === key)?.[1] || key,
                  points: policies[key]?.curve || [],
                }))}
              />
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table className="ops-table is-compact" style={{ minWidth: 580 }}>
                <thead>
                  <tr style={{ textAlign: 'left', color: C.muted, borderBottom: `1px solid ${C.line}` }}>
                    <th scope="col">Measure</th>
                    {POLICIES.map(([key, label]) => <th scope="col" key={key}>{policies[key]?.label || label}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['Time-weighted availability', key => {
                      const value = (policies[key]?.metrics || simulation.policy_metrics?.[key] || {}).time_weighted_average_availability_pct;
                      return value == null ? 'N/A' : `${metric(value, 3)}%`;
                    }],
                    ['Available aircraft-hours', key => metric((policies[key]?.metrics || simulation.policy_metrics?.[key] || {}).available_aircraft_hours)],
                    ['Aircraft downtime-hours', key => metric((policies[key]?.metrics || simulation.policy_metrics?.[key] || {}).aircraft_downtime_hours)],
                    ['Work orders completed', key => (policies[key]?.metrics || simulation.policy_metrics?.[key] || {}).work_orders_completed_by_horizon ?? '—'],
                    ['End availability', key => {
                      const curve = policies[key]?.curve || [];
                      const last = curve[curve.length - 1];
                      return !last ? '—' : `${last.available_aircraft}/${last.total_aircraft} · ${last.availability_pct == null ? 'N/A' : `${last.availability_pct}%`}`;
                    }],
                  ].map(([label, valueForPolicy]) => (
                    <tr key={label} style={{ borderTop: `1px solid ${C.line}` }}>
                      <th scope="row" style={{ textAlign: 'left', fontWeight: 500, color: C.muted }}>{label}</th>
                      {POLICIES.map(([key]) => <td key={key} style={{ color: C.text }}>{valueForPolicy(key)}</td>)}
                    </tr>
                  ))}
                  <tr>
                    <th scope="row" style={{ textAlign: 'left', fontWeight: 500, color: C.muted }}>Allocation assumption</th>
                    {POLICIES.map(([key]) => <td key={key} style={{ color: C.muted, fontSize: 11 }}>{policies[key]?.new_allocations_enabled ? 'New allocation assumed immediately approved' : 'No new allocations; existing work may progress'}</td>)}
                  </tr>
                </tbody>
              </table>
            </div>
            {availabilityComparison === 'tie' && <div style={{ marginTop: 10, color: C.warn, fontSize: 12 }}>The policies tie on time-weighted availability in this snapshot; proposed allocation does not improve this readiness measure.</div>}
            {availabilityComparison === 'unavailable' && <div style={{ marginTop: 10, color: C.muted, fontSize: 12 }}>Time-weighted availability is unavailable for one or more policies in this snapshot; policies cannot be compared on this measure.</div>}
            <div style={{ marginTop: 10, color: C.muted, fontSize: 11 }}>{completionSets}. Completion is maintenance progress, not proof of aircraft return-to-service; availability follows the backend classifier and fixed prediction.</div>
            {(comparison.length > 0 || points.length > 0 || (simulation.assumptions || []).length > 0) && (
              <details style={{ marginTop: 10, color: C.muted, fontSize: 11 }}>
                <summary style={{ cursor: 'pointer', color: C.text2 }}>Event timeline and simulation assumptions</summary>
                {comparison.length > 0 && (
                  <div style={{ marginTop: 10, overflowX: 'auto' }}>
                    <div className="ops-label" style={{ marginBottom: 5 }}>Availability by hour</div>
                    <table className="ops-table is-compact" style={{ minWidth: 520 }}>
                      <thead><tr><th>Hour</th>{POLICIES.map(([key, label]) => <th key={key}>{label}</th>)}</tr></thead>
                      <tbody>{comparison.map((row, index) => (
                        <tr key={`${row.hours}-${index}`} style={{ borderTop: `1px solid ${C.line}` }}>
                          <td>{row.hours}h</td>
                          {POLICIES.map(([key]) => <td key={key}>{row[key]?.available_aircraft ?? '—'}/{simulation.total_aircraft} · {row[key]?.availability_pct == null ? 'N/A' : `${row[key].availability_pct}%`}</td>)}
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                )}
                {points.length > 0 && (
                  <div style={{ marginTop: 10 }}>
                    <div className="ops-label" style={{ marginBottom: 5 }}>Maintenance events · aircraft availability shown separately</div>
                    {points.map((point, index) => (
                      <div key={`${point.key}-${point.hours}-${index}`} style={{ padding: '5px 0', borderTop: `1px solid ${C.line}` }}>
                        <b style={{ color: C.text2 }}>{point.policy}</b> at {point.hours}h · {point.started.length ? `started ${point.started.join(', ')}` : ''}{point.started.length && point.completed.length ? ' · ' : ''}{point.completed.length ? `completed ${point.completed.join(', ')}` : ''} · availability {point.available}/{point.total} ({point.pct == null ? 'N/A' : `${point.pct}%`})
                      </div>
                    ))}
                  </div>
                )}
                {(simulation.assumptions || []).length > 0 && <div style={{ marginTop: 10 }}>Assumptions: {simulation.assumptions.join('; ')}</div>}
              </details>
            )}
          </>
        )}
      </div>
    </section>
  );
}
