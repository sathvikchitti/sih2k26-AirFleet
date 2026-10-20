import React from 'react';
import { api, baseName, etaText, healthScoreText, rulText } from '../services/api.js';
import { ActionButton, Badge, DataError, KpiCard, PageHeader, SectionTitle, StatusMsg, priorityColor, riskColor, statusColor } from '../components/ui.jsx';
import ReadinessSimulationPanel from '../components/ReadinessSimulationPanel.jsx';
import ResourceForecastPanel from '../components/ResourceForecastPanel.jsx';
import EvaluationSummaryPanel from '../components/EvaluationSummaryPanel.jsx';
import RiskPolicyNote from '../components/RiskPolicyNote.jsx';
import { C } from '../theme.js';
import { FleetStatusBar } from '../components/charts.jsx';

const finiteMetric = value => typeof value === 'number' && Number.isFinite(value);
const percentLabel = value => finiteMetric(value) ? `${value.toFixed(1)}%` : '—';
const countLabel = value => finiteMetric(value) ? String(value) : '—';
const readinessColor = (rate, target, gap) => {
  if (!finiteMetric(rate) || !finiteMetric(target) || !finiteMetric(gap)) return C.muted;
  if (rate === 0 && target > 0) return C.crit;
  if (gap === 0 && rate >= target) return C.ok;
  if (gap > 0) return C.warn;
  return C.muted;
};

export function MissionReadinessBand({ fleet }) {
  if (!fleet) return null;
  const metrics = [
    ['Mission capable', percentLabel(fleet.mission_capable_rate_pct), 'Currently AVAILABLE aircraft'],
    ['Readiness target', percentLabel(fleet.readiness_target_pct), 'Backend-defined target'],
    ['Gap to target', finiteMetric(fleet.gap_to_target_pct) ? `${fleet.gap_to_target_pct.toFixed(1)} pp` : '—', 'Percentage-point shortfall'],
    ['NMCS proxy', countLabel(fleet.nmcs_count), 'Aircraft blocked by component supply'],
    ['Down for maintenance', countLabel(fleet.aircraft_down_for_maintenance), 'MAINTENANCE + WAITING status'],
  ];
  return (
    <section aria-label="Mission readiness metrics" className="ops-metric-strip" style={{ marginTop: 12 }}>
      {metrics.map(([label, value, sub]) => (
        <div key={label}>
          <div className="ops-label">{label}</div>
          <div className="ops-metric-value" style={{ color: label === 'Gap to target' ? readinessColor(fleet.mission_capable_rate_pct, fleet.readiness_target_pct, fleet.gap_to_target_pct) : C.text }}>{value}</div>
          <div className="ops-metric-sub">{sub}</div>
        </div>
      ))}
    </section>
  );
}

// Dashboard hero: the north-star number with a HUD-style tick scale and the
// backend readiness target marked on it.
export function ReadinessReadout({ fleet, aircraft }) {
  if (!fleet) return null;
  const pct = finiteMetric(fleet.availability_pct) ? fleet.availability_pct : null;
  const target = finiteMetric(fleet.readiness_target_pct) ? fleet.readiness_target_pct : null;
  const clamp = v => Math.max(0, Math.min(100, v));
  const color = pct == null ? C.muted : target != null && pct < target ? C.warn : C.hud;
  return (
    <section className="ops-readout" aria-label="Fleet availability">
      <div>
        <div className="ops-label">Fleet availability</div>
        <div className="ops-readout-value" style={{ color, marginTop: 12 }}>
          {pct == null ? '—' : <>{pct}<small>%</small></>}
        </div>
        <div className="ops-readout-meta">
          <b>{fleet.available}</b> of <b>{fleet.total}</b> aircraft available · <b>{fleet.high_risk ?? fleet.at_risk}</b> high-risk
        </div>
      </div>
      <div className="ops-scale" role="img" aria-label={`Availability ${pct ?? 'unavailable'}%${target != null ? `, readiness target ${target}%` : ''}`}>
        <div className="ops-scale-track">
          {pct != null && <div className="ops-scale-fill" style={{ width: clamp(pct) + '%', background: color }} />}
          {target != null && <div className="ops-scale-target" style={{ left: clamp(target) + '%' }}><span>Target {percentLabel(target)}</span></div>}
        </div>
        <div className="ops-scale-ticks" />
        <div className="ops-scale-labels"><span>0</span><span>25</span><span>50</span><span>75</span><span>100</span></div>
        {aircraft && aircraft.length ? <div style={{ marginTop: 22 }}><div className="ops-label" style={{ marginBottom: 8 }}>Fleet status mix</div><FleetStatusBar aircraft={aircraft} /></div> : null}
      </div>
    </section>
  );
}

export function BaseMissionReadiness({ base }) {
  const rate = base?.mission_capable_rate_pct;
  const target = base?.readiness_target_pct;
  const hasRate = finiteMetric(rate);
  const hasTarget = finiteMetric(target);
  const metricColor = readinessColor(rate, target, base?.gap_to_target_pct);
  const barWidth = hasRate ? Math.max(0, Math.min(100, rate)) : 0;
  const targetX = hasTarget ? Math.max(0, Math.min(100, target)) : null;
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, fontSize: 12 }}>
        <span className="ops-label">Mission capable</span>
        <b style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>{percentLabel(rate)}</b>
      </div>
      <svg viewBox="0 0 100 14" preserveAspectRatio="none" role="img" aria-label={`${base?.name || base?.id || 'Base'} mission capable ${percentLabel(rate)}${hasTarget ? `, readiness target ${percentLabel(target)}` : ', readiness target unavailable'}`} style={{ display: 'block', width: '100%', height: 16, marginTop: 6, overflow: 'visible' }}>
        <rect x="0" y="4" width="100" height="6" fill={C.deck} stroke={C.line2} strokeWidth="0.5" vectorEffect="non-scaling-stroke" />
        {hasRate && <rect x="0" y="4" width={barWidth} height="6" fill={metricColor} />}
        {hasTarget && <line x1={targetX} x2={targetX} y1="0" y2="14" stroke={C.text} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />}
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 11.5, color: C.muted, marginTop: 4 }}>
        <span style={{ color: metricColor }}>{finiteMetric(base?.gap_to_target_pct) ? `Gap ${base.gap_to_target_pct.toFixed(1)} pp` : 'Gap unavailable'}</span>
        <span>{hasTarget ? `Target ${percentLabel(target)}` : 'Target unavailable'}</span>
      </div>
      <div style={{ fontSize: 11.5, color: C.muted, marginTop: 10, paddingTop: 10, borderTop: `1px solid ${C.line}` }}>
        {countLabel(base?.nmcs_count)} NMCS supply-blocked · {countLabel(base?.aircraft_down_for_maintenance)} down for maintenance
      </div>
    </div>
  );
}

export default function CommanderDashboard({ onOpenAircraft, refreshKey }) {
  const [fleet, setFleet] = React.useState(null);
  const [aircraft, setAircraft] = React.useState([]);
  const [rec, setRec] = React.useState(null);
  const [transfers, setTransfers] = React.useState([]);
  const [workOrders, setWorkOrders] = React.useState([]);
  const [recommendationTarget, setRecommendationTarget] = React.useState(null);
  const [scenario, setScenario] = React.useState(null);
  const [shortages, setShortages] = React.useState(null);
  const [shortageError, setShortageError] = React.useState(null);
  const [recommendationError, setRecommendationError] = React.useState(null);
  const [msg, setMsg] = React.useState('');
  const [loadError, setLoadError] = React.useState(null);
  const [isLoading, setIsLoading] = React.useState(true);

  const load = async () => {
    setIsLoading(true);
    setLoadError(null);
    setRecommendationError(null);
    setFleet(null);
    setAircraft([]);
    setRec(null);
    setShortages(null);
    setShortageError(null);
    try {
      const [nextFleet, nextAircraft, nextTransfers, nextWorkOrders] = await Promise.all([
        api.getFleet(), api.getAircraft(), api.getTransfers(), api.getWorkOrders(),
      ]);
      setFleet(nextFleet);
      setAircraft(nextAircraft);
      setTransfers(nextTransfers);
      setWorkOrders(nextWorkOrders || []);

      const pendingWorkOrders = (nextWorkOrders || [])
        .filter(wo => !['COMPLETED', 'CANCELLED', 'CANCELED'].includes(String(wo.status || '').toUpperCase()) && wo.required_component);
      const priorityRank = wo => ({ CRITICAL: 0, HIGH: 1, URGENT: 1, MEDIUM: 2, NORMAL: 3, LOW: 4 }[String(wo.priority || '').toUpperCase()] ?? 5);
      pendingWorkOrders.sort((a, b) => priorityRank(a) - priorityRank(b));
      const target = pendingWorkOrders[0] || null;
      setRecommendationTarget(target);
      if (target?.id && !target.active_transfer_id) {
        try { setRec(await api.getWorkOrderRecommendation(target.id)); }
        catch (e) { setRecommendationError(e); }
      }
    } catch (e) { setLoadError(e); }

    try {
      const demand = await api.getResourceDemand();
      setShortages(Array.isArray(demand?.shortages) ? demand.shortages : null);
      setShortageError(null);
    } catch (e) {
      setShortages(null);
      setShortageError(e);
    }
    try { setScenario(await api.getDemoScenario()); }
    catch { setScenario(null); }
    setIsLoading(false);
  };
  React.useEffect(() => { load(); }, [refreshKey]);

  const approve = async () => {
    if (!recommendationTarget?.id || recommendationTarget.active_transfer_id || !rec?.recommended) return;
    setMsg('Requesting approval…');
    try {
      const r = await api.approveWorkOrderRecommendation(recommendationTarget.id);
      setMsg(`Approved: ${r.transfer.part_number} ${r.transfer.source_base} → ${r.transfer.dest_base} · ${r.transfer.id} IN TRANSIT (ETA ${r.transfer.eta_hours}h)`);
      load();
    } catch (e) { setMsg(e?.message || 'Transfer approval failed.'); }
  };

  const atRisk = aircraft.filter(a => a.health && ['HIGH', 'CRITICAL', 'MEDIUM'].includes(a.health.risk_level))
    .sort((x, y) => x.health.health_score - y.health.health_score);
  const targetTransfer = recommendationTarget?.active_transfer_id
    ? transfers.find(transfer => String(transfer.id) === String(recommendationTarget.active_transfer_id))
    : null;
  const targetTransferStatus = String(targetTransfer?.status || '').toUpperCase();
  const targetWorkOrderStatus = String(recommendationTarget?.status || '').toUpperCase();

  return (
    <div>
      <PageHeader
        title="Fleet decision support"
        subtitle={<>System recommends. Human commands. The <b>recommended action</b> below is advisory.</>}
      />
      {loadError && <div style={{ marginTop: 16 }}><DataError error={loadError}>Fleet or work-order data could not be loaded.</DataError></div>}
      {fleet && <ReadinessReadout fleet={fleet} aircraft={aircraft} />}
      {fleet && (
        <div className="ops-kpi-grid" style={{ marginTop: 12 }}>
          <KpiCard label="Aircraft available" value={fleet.available + '/' + fleet.total} accent={C.ok} />
          <KpiCard label="Aircraft at risk" value={fleet.at_risk} accent={C.crit} />
          <KpiCard label="Active maintenance" value={fleet.maintenance} accent={C.info} />
          <KpiCard label="Resource shortages" value={shortages ? shortages.length : '—'} sub={shortageError ? 'unavailable' : 'from resource demand'} accent={shortages?.length ? C.warn : undefined} />
        </div>
      )}
      {fleet && <MissionReadinessBand fleet={fleet} />}
      {scenario?.operational_data_synthetic && scenario?.scenario_id && (
        <div className="ops-note" style={{ marginTop: 10 }}>
          {scenario.label || 'Synthetic fleet operations scenario'} · operational states are synthetic; aircraft health and RUL remain model predictions.
        </div>
      )}

      <SectionTitle>Priority maintenance action</SectionTitle>
      <div className="ops-card ops-callout" style={{ '--callout': C.warn }}>
        <div className="ops-label" style={{ color: C.warn }}>Recommended action · active work order</div>
        {isLoading ? (
          <div className="ops-loading">Loading fleet and active work-order data…</div>
        ) : loadError ? (
          <div style={{ marginTop: 8, fontSize: 13, color: C.crit }}>Active maintenance action unavailable because fleet or work-order data could not be loaded.</div>
        ) : recommendationTarget?.active_transfer_id ? (
          <div style={{ marginTop: 8, fontSize: 13, color: C.text2 }}>
            {targetTransferStatus === 'IN_TRANSIT'
              ? <>Work order {recommendationTarget.id} for {recommendationTarget.aircraft_id} has transfer {recommendationTarget.active_transfer_id} in transit and is awaiting receipt.</>
              : targetTransferStatus === 'RECEIVED'
                ? <>Transfer {recommendationTarget.active_transfer_id} was received for work order {recommendationTarget.id} on {recommendationTarget.aircraft_id}. Work order status: {targetWorkOrderStatus || 'unavailable'}; continue with the maintenance action shown on the aircraft.</>
                : targetTransferStatus === 'PENDING_APPROVAL'
                  ? <>Transfer {recommendationTarget.active_transfer_id} for work order {recommendationTarget.id} is pending approval.</>
                  : <>Work order {recommendationTarget.id} for {recommendationTarget.aircraft_id} references transfer {recommendationTarget.active_transfer_id}{targetTransferStatus ? ` (${targetTransferStatus})` : ', status unavailable'}; review its current status before acting.</>}
            <div style={{ marginTop: 12 }}><ActionButton onClick={() => onOpenAircraft(recommendationTarget.aircraft_id)}>View aircraft</ActionButton></div>
          </div>
        ) : rec?.recommended ? (
          <>
            <div className="ops-action-title">
              <span className="ops-id">{recommendationTarget.aircraft_id}</span>
              <span>WO {recommendationTarget.id}</span>
              <Badge color={priorityColor(recommendationTarget.priority)}>{recommendationTarget.priority || 'Priority unavailable'}</Badge>
            </div>
            <div className="ops-action-route">
              <b>{rec.required_component || recommendationTarget.required_component}</b> from <b>{baseName(rec.recommended.source_base || rec.recommended.base_id || rec.recommended.donor_base)}</b>
              <span className="ops-action-eta">ETA {rec.recommended.eta_hours}h</span>
            </div>
            <ul className="ops-reasons">
              {rec.recommended.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
            <div className="ops-note" style={{ marginTop: 12 }}>
              Alternatives: {(rec.candidates || []).slice(1).map(c => `${baseName(c.source_base || c.base_id || c.donor_base)} (${c.condition_pct == null ? '—' : `${c.condition_pct}%`}, ETA ${etaText(c.eta_hours)})`).join(' · ') || 'none viable'}
            </div>
            <div style={{ display: 'flex', gap: 10, marginTop: 16, flexWrap: 'wrap' }}>
              <ActionButton primary onClick={approve}>Approve transfer</ActionButton>
              <ActionButton onClick={() => onOpenAircraft(recommendationTarget.aircraft_id)}>View aircraft</ActionButton>
            </div>
            <StatusMsg>{msg}</StatusMsg>
          </>
        ) : recommendationError ? (
          <div style={{ marginTop: 8, fontSize: 13, color: C.crit }}>Recommendation unavailable: {recommendationError.message}</div>
        ) : recommendationTarget ? (
          <div style={{ marginTop: 8, fontSize: 13, color: C.text2 }}>
            No feasible transfer is currently recommended for work order {recommendationTarget.id} on {recommendationTarget.aircraft_id} ({recommendationTarget.required_component}).
            {rec?.rejected?.length ? <ul className="ops-reasons">{rec.rejected.map((item, i) => <li key={i}>{baseName(item.source_base || item.base_id)} — {item.reason || item.detail}</li>)}</ul> : null}
            <div style={{ marginTop: 12 }}><ActionButton onClick={() => onOpenAircraft(recommendationTarget.aircraft_id)}>View aircraft</ActionButton></div>
          </div>
        ) : (
          <div style={{ marginTop: 8, fontSize: 13, color: C.muted }}>No active component work order is available for recommendation.</div>
        )}
      </div>

      <SectionTitle>Base readiness</SectionTitle>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: 12 }}>
        {(fleet?.bases || []).map(b => (
          <div key={b.id} className="ops-card" style={{ padding: '16px 18px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10 }}>
              <div className="ops-card-title">{b.name}</div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 38, fontWeight: 700, lineHeight: 1, color: b.availability_pct >= 85 ? C.ok : C.warn }}>{b.availability_pct}%</div>
            </div>
            <div style={{ fontSize: 12, color: C.muted, marginTop: 4 }}>{b.available}/{b.aircraft_count} available · {b.at_risk} at risk · {b.maintenance} mx</div>
            <BaseMissionReadiness base={b} />
          </div>
        ))}
      </div>

      <SectionTitle>Fleet risk — high-risk aircraft</SectionTitle>
      <RiskPolicyNote refreshKey={refreshKey} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: 12 }}>
        {atRisk.slice(0, 4).map(a => (
          <button key={a.id} onClick={() => onOpenAircraft(a.id)} className={`ops-tile${['HIGH', 'CRITICAL'].includes(a.health.risk_level) ? ' is-alert' : ''}`}>
            <div className="ops-tile-head"><span className="ops-tile-title">{a.id}</span><Badge color={riskColor(a.health.risk_level)}>{a.health.risk_level} RISK</Badge></div>
            <div className="ops-tile-meta">{baseName(a.base_id)} · RUL {rulText(a.health)} · Health {healthScoreText(a.health)}</div>
            <div style={{ fontSize: 12.5, marginTop: 10, color: C.text2 }}>Required: <b style={{ color: C.text }}>{a.health.required_component || a.required_component || '—'}</b></div>
          </button>
        ))}
      </div>

      <SectionTitle>Transfers</SectionTitle>
      <div className="ops-card ops-table-scroll">
        <table className="ops-table" style={{ minWidth: 520 }}>
          <thead><tr>
            <th>ID</th><th>Part</th><th>Route</th><th>Status</th><th style={{ textAlign: 'right' }}>ETA</th>
          </tr></thead>
          <tbody>
            {transfers.map(t => (
              <tr key={t.id} className="ops-table-row">
                <td className="ops-id">{t.id}</td><td>{t.part_number}</td>
                <td>{baseName(t.source_base)} → {baseName(t.dest_base)}</td>
                <td><Badge color={statusColor(t.status)}>{String(t.status || '—').replace(/_/g, ' ')}</Badge></td>
                <td className="ops-number" style={{ textAlign: 'right' }}>{etaText(t.eta_hours)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ResourceForecastPanel canRequestMove={false} refreshKey={refreshKey} />
      <EvaluationSummaryPanel refreshKey={refreshKey} />
      <ReadinessSimulationPanel refreshKey={refreshKey} />
    </div>
  );
}
