import React from 'react';
import { api, baseName, healthScoreText, rulText, rulUnit, rulValue } from '../../services/api.js';
import { useFleetViews, useLoad } from '../../services/hooks.js';
import {
  ActionButton, Badge, DataError, Empty, KpiCard, Loading, PageHeader, RiskBadge,
  StatusMsg, riskColor,
} from '../../components/ui.jsx';

// Commander — Recommendations: every aircraft the ML service has flagged, with
// a ranked donor analysis for the component it needs. This is where the human
// in the loop approves a transfer.
export default function RecommendationsView({ onOpenAircraft, refreshKey, refresh }) {
  const { aircraft, loading, predictionError } = useFleetViews(refreshKey);
  const [workOrders] = useLoad(() => api.getWorkOrders(), refreshKey);
  const [msg, setMsg] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  if (loading) return <Loading>Loading recommendations…</Loading>;
  if (predictionError) return <DataError error={predictionError}>Recommendations are unavailable because the selected ML provider did not return aircraft predictions.</DataError>;

  const activeWorkOrderByAircraft = new Map((workOrders || [])
    .filter(wo => String(wo.status || '').toUpperCase() !== 'COMPLETED' && wo.required_component)
    .map(wo => [wo.aircraft_id, wo]));
  const flagged = (aircraft || [])
    .map(a => ({ ...a, activeWorkOrder: activeWorkOrderByAircraft.get(a.id) || null }))
    .filter(a => a.health?.required_component || a.required_component || a.activeWorkOrder?.required_component)
    .sort((x, y) => {
      const rank = a => ({ CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 }[a.health?.risk_level || 'LOW']);
      const dr = rank(x) - rank(y);
      return dr !== 0 ? dr : (rulValue(x.health) ?? 999) - (rulValue(y.health) ?? 999);
    });

  const approve = async (aircraft) => {
    setBusy(true);
    setMsg('Approving transfer for ' + aircraft.id + '…');
    try {
      const r = aircraft.activeWorkOrder?.id
        ? await api.approveWorkOrderRecommendation(aircraft.activeWorkOrder.id)
        : await api.approveRecommendation(aircraft.id);
      const t = r.transfer || {};
      setMsg(`Approved: ${t.part_number} ${baseName(t.source_base)} → ${baseName(t.dest_base)} (${t.id}) IN TRANSIT, ETA ${t.eta_hours}h`);
      refresh();
    } catch (e) {
      setMsg(e?.message || 'Approval failed. Check the backend connection and try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Recommendations"
        subtitle="Advisory only — the system proposes, the commander disposes. Each card ranks candidate donor bases for the component an aircraft needs next."
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, margin: '14px 0' }}>
        <KpiCard label="Aircraft Flagged" value={flagged.length} />
        <KpiCard label="Critical" value={flagged.filter(a => a.health?.risk_level === 'CRITICAL' || a.health?.risk_level === 'HIGH').length} accent="#e05c5c" />
        <KpiCard label="Parts In Play" value={new Set(flagged.map(a => a.health?.required_component || a.required_component || a.activeWorkOrder?.required_component)).size} accent="#d8a93d" />
      </div>

      <StatusMsg>{msg}</StatusMsg>

      {flagged.length === 0 ? (
        <div className="ops-card"><Empty>No aircraft currently require a component change.</Empty></div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {flagged.map(a => (
            <RecommendationCard
              key={a.id}
              aircraft={a}
              refreshKey={refreshKey}
              onOpen={onOpenAircraft}
              onApprove={approve}
              busy={busy}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function RecommendationCard({ aircraft, refreshKey, onOpen, onApprove, busy }) {
  const [rec, recErr] = useLoad(
    () => aircraft.activeWorkOrder?.active_transfer_id
      ? Promise.resolve(null)
      : aircraft.activeWorkOrder?.id
      ? api.getWorkOrderRecommendation(aircraft.activeWorkOrder.id)
      : api.getRecommendation(aircraft.id),
    refreshKey,
    [aircraft.activeWorkOrder?.id, aircraft.activeWorkOrder?.active_transfer_id]
  );
  const [impact] = useLoad(
    () => rec?.work_order_id ? api.getImpactPreview(rec.work_order_id) : Promise.resolve(null),
    refreshKey,
    [rec?.work_order_id]
  );
  const part = aircraft.health?.required_component || aircraft.required_component || aircraft.activeWorkOrder?.required_component;
  const h = aircraft.health || {};
  const requiredByHours = aircraft.activeWorkOrder?.required_by_flight_hours
    ?? aircraft.required_by_flight_hours
    ?? (rulUnit(h) === 'flight hours' ? aircraft.required_by_hours : null);
  const requiredByCycles = aircraft.activeWorkOrder?.rul_unit === 'cycles'
    ? aircraft.activeWorkOrder?.required_by_rul
    : aircraft.required_by_cycles;
  const componentSource = String(aircraft.activeWorkOrder?.component_source || '').toLowerCase();
  const cand = rec?.candidates || [];
  const infeasible = rec?.infeasible_candidates || rec?.rejected_candidates || rec?.rejected || [];
  const selectedImpact = impact?.options?.find(option => option.source_base === (rec?.recommended?.source_base || rec?.recommended?.base_id || rec?.recommended?.donor_base));
  const projectedAvailability = selectedImpact?.projected_fleet_availability_pct
    ?? selectedImpact?.projected_availability_pct
    ?? impact?.recommended?.expected_fleet_availability_pct;
  const projectedAt = selectedImpact?.projected_at_hours ?? impact?.recommended?.projected_at_hours;

  return (
    <div className="ops-card" style={{ padding: 16, borderLeft: '4px solid ' + riskColor(h.risk_level) }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <b style={{ fontSize: 18 }}>{aircraft.id}</b>
          {h.risk_level && <RiskBadge risk={h.risk_level} />}
          {aircraft.activeWorkOrder && <Badge color="#4f9cf0">ACTIVE WORK ORDER</Badge>}
          <Badge color={aircraft.status === 'AVAILABLE' ? '#3fb97f' : '#d8a93d'}>{String(aircraft.status).replace(/_/g, ' ')}</Badge>
          <span style={{ fontSize: 12, color: '#8b94a3' }}>{baseName(aircraft.base_id)} · {aircraft.type}</span>
        </div>
        <div style={{ fontSize: 12, color: '#8b94a3', textAlign: 'right' }}>
          Health <b style={{ color: riskColor(h.risk_level) }}>{healthScoreText(h)}</b> · RUL <b>{rulText(h)}</b>
          <br />needs <b style={{ color: '#d8a93d' }}>{part}</b>
          {['human_selected', 'fixture_scenario'].includes(componentSource) ? <><br /><span style={{ color: '#8b94a3' }}>{componentSource === 'human_selected' ? 'Component selected during human triage; not an ML output.' : 'Component set for the synthetic operational scenario; not an ML output.'}</span></> : null}
          {requiredByHours != null ? <> within <b>{requiredByHours}h</b></> : requiredByCycles != null ? <> within <b>{requiredByCycles} cycles</b></> : null}
        </div>
      </div>

      {recErr ? (
            <div style={{ marginTop: 10, fontSize: 12, color: '#e05c5c' }}>Could not load donor analysis: {recErr.message || 'request failed'}.</div>
      ) : !rec ? (
        <div style={{ marginTop: 10, fontSize: 12, color: '#8b94a3' }}>
          {aircraft.activeWorkOrder?.active_transfer_id
            ? `Transfer ${aircraft.activeWorkOrder.active_transfer_id} is already active; continue with Logistics receipt.`
            : 'Analysing donor bases…'}
        </div>
      ) : cand.length === 0 ? (
        <div style={{ marginTop: 12, fontSize: 13, color: '#e05c5c' }}>
          {infeasible.length ? `No feasible donor is available for ${part}. Review the rejected options below.` : `No base holds a serviceable ${part} — no viable donor. This aircraft will stay grounded until stock is sourced externally.`}
        </div>
      ) : (
        <>
          <div style={{ marginTop: 12, fontSize: 15, fontWeight: 800 }}>
            Source {part} from {baseName(rec.recommended?.donor_base || rec.recommended?.source_base || rec.recommended?.base_id)} — ETA {rec.recommended?.eta_hours}h
          </div>
          {rec.recommended?.reasons && (
            <ul style={{ fontSize: 13, color: '#c6ccd6', marginTop: 8, paddingLeft: 18 }}>
              {rec.recommended.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          )}
          {impact && (
            <div style={{ marginTop: 10, padding: 10, border: '1px solid #2a3444', borderRadius: 8, fontSize: 12, color: '#8b94a3' }}>
              <b style={{ color: '#c6ccd6' }}>Availability projection · estimate</b>
              <div style={{ marginTop: 4 }}>
                Current fleet availability: <b>{impact.current_fleet_availability_pct ?? '—'}%</b>
                {projectedAvailability != null ? <> · Projected: <b>{projectedAvailability}%</b></> : null}
                {projectedAt != null ? <> at {projectedAt}h</> : null}
              </div>
              {Array.isArray(impact.options) && impact.options.map((option, i) => (
                <div key={option.source_base || option.donor_base || i} style={{ marginTop: 3 }}>
                  {baseName(option.source_base || option.donor_base || 'Unknown base')} donor impact: {option.donor_base_projection?.stockout_risk || option.donor_impact || '—'}
                  {option.donor_base_projection?.transferable_units_after != null ? <> · {option.donor_base_projection.transferable_units_after} transferable units after</> : null}
                  {option.source_base_projection?.current_availability_pct != null ? <> · donor availability {option.source_base_projection.current_availability_pct}% stays unchanged</> : null}
                  {option.destination_base_projection?.projected_availability_pct != null ? <> · destination projects to {option.destination_base_projection.projected_availability_pct}%</> : null}
                  {(option.projected_fleet_availability_pct ?? option.projected_availability_pct) != null ? <> · projected fleet {option.projected_fleet_availability_pct ?? option.projected_availability_pct}% at {option.projected_at_hours}h</> : null}
                </div>
              ))}
              {impact.assumptions?.length ? <div style={{ marginTop: 4 }}>Assumptions: {impact.assumptions.join('; ')}</div> : null}
            </div>
          )}
          <div style={{ marginTop: 12, overflow: 'hidden', border: '1px solid #2a3444', borderRadius: 8 }}>
            <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ textAlign: 'left', color: '#8b94a3', fontSize: 10 }}>
                  <th style={{ padding: 8 }}>Rank</th><th>Donor</th><th style={{ textAlign: 'right' }}>Free qty</th>
                  <th style={{ textAlign: 'right' }}>Condition</th><th style={{ textAlign: 'right' }}>Distance</th>
                  <th style={{ textAlign: 'right' }}>ETA</th><th style={{ textAlign: 'right' }}>Expected downtime</th>
                </tr>
              </thead>
              <tbody>
                {cand.map((c, i) => (
                  <tr key={c.donor_base || c.source_base || c.base_id} style={{ borderTop: '1px solid #2a3444', background: i === 0 ? '#151b24' : 'transparent' }}>
                    <td style={{ padding: 8 }}>{i === 0 ? <b style={{ color: '#d8a93d' }}>BEST</b> : '#' + (i + 1)}</td>
                    <td>{baseName(c.donor_base || c.source_base || c.base_id)}</td>
                    <td style={{ textAlign: 'right' }}>{c.quantity_available}</td>
                    <td style={{ textAlign: 'right' }}>{c.condition_pct}%</td>
                    <td style={{ textAlign: 'right' }}>{c.distance_km} km</td>
                    <td style={{ textAlign: 'right' }}>{c.eta_hours}h</td>
                    <td style={{ textAlign: 'right' }}>{c.expected_downtime_hours}h</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            <ActionButton onClick={() => onOpen(aircraft.id)}>View Details</ActionButton>
            {aircraft.activeWorkOrder?.active_transfer_id ? (
              <span style={{ alignSelf: 'center', color: '#8b94a3', fontSize: 12 }}>Transfer {aircraft.activeWorkOrder.active_transfer_id} is already active; continue with Logistics receipt.</span>
            ) : (
              <ActionButton primary disabled={busy} onClick={() => onApprove(aircraft)}>
                {busy ? 'Approving…' : 'Approve Transfer'}
              </ActionButton>
            )}
          </div>
        </>
      )}
      {rec && infeasible.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div className="ops-label" style={{ color: '#e05c5c' }}>Infeasible options · not available for approval</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
            {infeasible.map((c, i) => (
              <div key={c.donor_base || c.source_base || i} style={{ fontSize: 12, color: '#8b94a3' }}>
                <b>{baseName(c.donor_base || c.source_base || c.base_id || 'Unknown base')}</b> — {c.reason || c.detail || 'Rejected by operational feasibility checks.'}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
