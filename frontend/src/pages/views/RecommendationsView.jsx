import React from 'react';
import { api, baseName, healthScoreText, rulText, rulUnit, rulValue } from '../../services/api.js';
import { useFleetViews, useLoad } from '../../services/hooks.js';
import {
  ActionButton, Badge, DataError, Empty, KpiCard, Loading, PageHeader, RiskBadge,
  StatusMsg, riskColor,
} from '../../components/ui.jsx';
import { C } from '../../theme.js';

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

      <div className="ops-kpi-grid">
        <KpiCard label="Aircraft Flagged" value={flagged.length} />
        <KpiCard label="Critical" value={flagged.filter(a => a.health?.risk_level === 'CRITICAL' || a.health?.risk_level === 'HIGH').length} accent={C.crit} />
        <KpiCard label="Parts In Play" value={new Set(flagged.map(a => a.health?.required_component || a.required_component || a.activeWorkOrder?.required_component)).size} accent={C.warn} />
      </div>

      <StatusMsg>{msg}</StatusMsg>

      {flagged.length === 0 ? (
        <div className="ops-card"><Empty>No aircraft currently require a component change.</Empty></div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 8 }}>
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
    <div className="ops-card ops-callout" style={{ '--callout': riskColor(h.risk_level) }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="ops-tile-title" style={{ fontSize: 22 }}>{aircraft.id}</span>
          {h.risk_level && <RiskBadge risk={h.risk_level} />}
          {aircraft.activeWorkOrder && <Badge color={C.info}>ACTIVE WORK ORDER</Badge>}
          <Badge color={aircraft.status === 'AVAILABLE' ? C.ok : C.warn}>{String(aircraft.status).replace(/_/g, ' ')}</Badge>
          <span style={{ fontSize: 12, color: C.muted }}>{baseName(aircraft.base_id)} · {aircraft.type}</span>
        </div>
        <div style={{ fontSize: 12.5, color: C.muted, textAlign: 'right', lineHeight: 1.6 }}>
          Health <b style={{ color: riskColor(h.risk_level) }}>{healthScoreText(h)}</b> · RUL <b>{rulText(h)}</b>
          <br />needs <b style={{ color: C.warn }}>{part}</b>
          {['human_selected', 'fixture_scenario'].includes(componentSource) ? <><br /><span style={{ color: C.muted }}>{componentSource === 'human_selected' ? 'Component selected during human triage; not an ML output.' : 'Component set for the synthetic operational scenario; not an ML output.'}</span></> : null}
          {requiredByHours != null ? <> within <b>{requiredByHours}h</b></> : requiredByCycles != null ? <><br />Event RUL <b>{rulText({ rul: requiredByCycles, rul_unit: 'cycles' })}</b></> : null}
        </div>
      </div>

      {recErr ? (
            <div style={{ marginTop: 10, fontSize: 12, color: C.crit }}>Could not load donor analysis: {recErr.message || 'request failed'}.</div>
      ) : !rec ? (
        <div style={{ marginTop: 10, fontSize: 12, color: C.muted }}>
          {aircraft.activeWorkOrder?.active_transfer_id
            ? `Transfer ${aircraft.activeWorkOrder.active_transfer_id} is already active; continue with Logistics receipt.`
            : 'Analysing donor bases…'}
        </div>
      ) : cand.length === 0 ? (
        <div style={{ marginTop: 12, fontSize: 13, color: C.crit }}>
          {infeasible.length ? `No feasible donor is available for ${part}. Review the rejected options below.` : `No base holds a serviceable ${part} — no viable donor. This aircraft will stay grounded until stock is sourced externally.`}
        </div>
      ) : (
        <>
          <div className="ops-action-route" style={{ marginTop: 16, fontSize: 16 }}>
            Source <b>{part}</b> from <b>{baseName(rec.recommended?.donor_base || rec.recommended?.source_base || rec.recommended?.base_id)}</b>
            <span className="ops-action-eta">ETA {rec.recommended?.eta_hours}h</span>
          </div>
          {rec.recommended?.reasons && (
            <ul className="ops-reasons">
              {rec.recommended.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          )}
          {impact && (
            <div style={{ marginTop: 14, padding: '12px 14px', border: `1px solid ${C.line}`, borderRadius: 2, background: C.deck, fontSize: 12, color: C.muted, lineHeight: 1.55 }}>
              <div className="ops-label" style={{ color: C.text2 }}>Availability projection · estimate</div>
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
          <div className="ops-table-scroll" style={{ marginTop: 14, border: `1px solid ${C.line}`, borderRadius: 2 }}>
            <table className="ops-table is-compact" style={{ minWidth: 560 }}>
              <thead>
                <tr>
                  <th>Rank</th><th>Donor</th><th style={{ textAlign: 'right' }}>Free qty</th>
                  <th style={{ textAlign: 'right' }}>Condition</th><th style={{ textAlign: 'right' }}>Distance</th>
                  <th style={{ textAlign: 'right' }}>ETA</th><th style={{ textAlign: 'right' }}>Expected downtime</th>
                </tr>
              </thead>
              <tbody>
                {cand.map((c, i) => (
                  <tr key={c.donor_base || c.source_base || c.base_id} className="ops-table-row" style={{ background: i === 0 ? `color-mix(in srgb, ${C.hud} 6%, transparent)` : undefined }}>
                    <td className="ops-id">{i === 0 ? <b style={{ color: C.hud }}>BEST</b> : '#' + (i + 1)}</td>
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
          <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
            <ActionButton onClick={() => onOpen(aircraft.id)}>View Details</ActionButton>
            {aircraft.activeWorkOrder?.active_transfer_id ? (
              <span style={{ alignSelf: 'center', color: C.muted, fontSize: 12 }}>Transfer {aircraft.activeWorkOrder.active_transfer_id} is already active; continue with Logistics receipt.</span>
            ) : (
              <ActionButton primary disabled={busy} onClick={() => onApprove(aircraft)}>
                {busy ? 'Approving…' : 'Approve Transfer'}
              </ActionButton>
            )}
          </div>
        </>
      )}
      {rec && infeasible.length > 0 && (
        <div style={{ marginTop: 16, paddingTop: 14, borderTop: `1px solid ${C.line}` }}>
          <div className="ops-label" style={{ color: C.crit }}>Infeasible options · not available for approval</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
            {infeasible.map((c, i) => (
              <div key={c.donor_base || c.source_base || i} style={{ fontSize: 12, color: C.muted }}>
                <b>{baseName(c.donor_base || c.source_base || c.base_id || 'Unknown base')}</b> — {c.reason || c.detail || 'Rejected by operational feasibility checks.'}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
