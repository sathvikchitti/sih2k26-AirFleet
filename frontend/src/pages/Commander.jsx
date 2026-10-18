import React from 'react';
import { api, baseName, etaText, healthScoreText, rulText } from '../services/api.js';
import { Badge, DataError, KpiCard, SectionTitle, riskColor } from '../components/ui.jsx';
import ReadinessSimulationPanel from '../components/ReadinessSimulationPanel.jsx';

const finiteMetric = value => typeof value === 'number' && Number.isFinite(value);
const percentLabel = value => finiteMetric(value) ? `${value.toFixed(1)}%` : '—';
const countLabel = value => finiteMetric(value) ? String(value) : '—';
const readinessColor = (rate, target, gap) => {
  if (!finiteMetric(rate) || !finiteMetric(target) || !finiteMetric(gap)) return '#8b94a3';
  if (rate === 0 && target > 0) return '#e05c5c';
  if (gap === 0 && rate >= target) return '#3fb97f';
  if (gap > 0) return '#d8a93d';
  return '#8b94a3';
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
    <section aria-label="Mission readiness metrics" style={{ marginTop: 12 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(145px,1fr))', gap: 10 }}>
        {metrics.map(([label, value, sub]) => (
          <div key={label} className="ops-card" style={{ padding: '10px 12px' }}>
            <div className="ops-label">{label}</div>
            <div style={{ fontSize: 23, fontWeight: 800, color: label === 'Gap to target' ? readinessColor(fleet.mission_capable_rate_pct, fleet.readiness_target_pct, fleet.gap_to_target_pct) : '#e6e9ee', marginTop: 3 }}>{value}</div>
            <div style={{ fontSize: 11, color: '#8b94a3', marginTop: 3 }}>{sub}</div>
          </div>
        ))}
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
    <div style={{ marginTop: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, fontSize: 12 }}>
        <span style={{ color: '#8b94a3' }}>Mission capable</span>
        <b>{percentLabel(rate)}</b>
      </div>
      <svg viewBox="0 0 100 14" role="img" aria-label={`${base?.name || base?.id || 'Base'} mission capable ${percentLabel(rate)}${hasTarget ? `, readiness target ${percentLabel(target)}` : ', readiness target unavailable'}`} style={{ display: 'block', width: '100%', height: 20, marginTop: 4, overflow: 'visible' }}>
        <rect x="0" y="3" width="100" height="8" rx="3" fill="#0a0e13" stroke="#2a3444" />
        {hasRate && <rect x="0" y="3" width={barWidth} height="8" rx="3" fill={metricColor} />}
        {hasTarget && <line x1={targetX} x2={targetX} y1="0" y2="14" stroke="#e6e9ee" strokeWidth="1.6" strokeDasharray="2 1" />}
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 11, color: '#8b94a3', marginTop: 2 }}>
        <span style={{ color: metricColor }}>{finiteMetric(base?.gap_to_target_pct) ? `Gap ${base.gap_to_target_pct.toFixed(1)} pp` : 'Gap unavailable'}</span>
        <span>{hasTarget ? `Target ${percentLabel(target)}` : 'Target unavailable'}</span>
      </div>
      <div style={{ fontSize: 11, color: '#8b94a3', marginTop: 6 }}>
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
      <h2 style={{ fontSize: 22, fontWeight: 800 }}>Commander — Fleet Decision Support</h2>
      <p style={{ color: '#8b94a3', fontSize: 13 }}>System recommends. Human commands. <b style={{ color: '#d8a93d' }}>RECOMMENDED ACTION</b> below is advisory.</p>
      {loadError && <DataError error={loadError}>Fleet or work-order data could not be loaded.</DataError>}
      {fleet && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12 }}>
          <KpiCard label="Fleet Availability" value={fleet.availability_pct + '%'} accent="#d8a93d" />
          <KpiCard label="Aircraft Available" value={fleet.available + '/' + fleet.total} />
          <KpiCard label="Aircraft At Risk" value={fleet.at_risk} accent="#e05c5c" />
          <KpiCard label="Active Maintenance" value={fleet.maintenance} accent="#4f9cf0" />
          <KpiCard label="Resource Shortages" value={shortages ? shortages.length : '—'} sub={shortageError ? 'unavailable' : 'from resource demand'} accent="#e05c5c" />
        </div>
      )}
      {fleet && <MissionReadinessBand fleet={fleet} />}
      {scenario?.operational_data_synthetic && scenario?.scenario_id && (
        <div style={{ marginTop: 10, fontSize: 12, color: '#8b94a3' }}>
          {scenario.label || 'Synthetic fleet operations scenario'} · operational states are synthetic; aircraft health and RUL remain model predictions.
        </div>
      )}

      <SectionTitle>Priority maintenance action</SectionTitle>
      <div className="ops-card" style={{ padding: 16, borderLeft: '4px solid #d8a93d' }}>
        <div className="ops-label">Recommended action · active work order</div>
        {isLoading ? (
          <div style={{ fontSize: 13, color: '#8b94a3' }}>Loading fleet and active work-order data…</div>
        ) : loadError ? (
          <div style={{ fontSize: 13, color: '#e05c5c' }}>Active maintenance action unavailable because fleet or work-order data could not be loaded.</div>
        ) : recommendationTarget?.active_transfer_id ? (
          <div style={{ fontSize: 13, color: '#8b94a3' }}>
            {targetTransferStatus === 'IN_TRANSIT'
              ? <>Work order {recommendationTarget.id} for {recommendationTarget.aircraft_id} has transfer {recommendationTarget.active_transfer_id} in transit and is awaiting receipt.</>
              : targetTransferStatus === 'RECEIVED'
                ? <>Transfer {recommendationTarget.active_transfer_id} was received for work order {recommendationTarget.id} on {recommendationTarget.aircraft_id}. Work order status: {targetWorkOrderStatus || 'unavailable'}; continue with the maintenance action shown on the aircraft.</>
                : targetTransferStatus === 'PENDING_APPROVAL'
                  ? <>Transfer {recommendationTarget.active_transfer_id} for work order {recommendationTarget.id} is pending approval.</>
                  : <>Work order {recommendationTarget.id} for {recommendationTarget.aircraft_id} references transfer {recommendationTarget.active_transfer_id}{targetTransferStatus ? ` (${targetTransferStatus})` : ', status unavailable'}; review its current status before acting.</>}
            <div style={{ marginTop: 8 }}><button onClick={() => onOpenAircraft(recommendationTarget.aircraft_id)} style={{ background: 'transparent', border: '1px solid #2a3444', color: '#e6e9ee', borderRadius: 7, padding: '7px 12px', cursor: 'pointer' }}>View aircraft</button></div>
          </div>
        ) : rec?.recommended ? (
          <>
            <div style={{ fontSize: 16, fontWeight: 800, marginTop: 6 }}>{recommendationTarget.aircraft_id} · WO {recommendationTarget.id} · {recommendationTarget.priority || 'Priority unavailable'} · {rec.required_component || recommendationTarget.required_component} from {baseName(rec.recommended.source_base || rec.recommended.base_id || rec.recommended.donor_base)} — ETA {rec.recommended.eta_hours}h</div>
            <ul style={{ fontSize: 13, color: '#c6ccd6', marginTop: 8, paddingLeft: 18 }}>
              {rec.recommended.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
            <div style={{ fontSize: 12, color: '#8b94a3', marginTop: 8 }}>
              Alternatives: {(rec.candidates || []).slice(1).map(c => `${baseName(c.source_base || c.base_id || c.donor_base)} (${c.condition_pct == null ? '—' : `${c.condition_pct}%`}, ETA ${etaText(c.eta_hours)})`).join(' · ') || 'none viable'}
            </div>
            <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
              <button onClick={() => onOpenAircraft(recommendationTarget.aircraft_id)} style={{ background: 'transparent', border: '1px solid #2a3444', color: '#e6e9ee', borderRadius: 7, padding: '8px 14px', cursor: 'pointer' }}>View aircraft</button>
              <button onClick={approve} style={{ background: '#d8a93d', border: 'none', color: '#111', fontWeight: 800, borderRadius: 7, padding: '8px 14px', cursor: 'pointer' }}>Approve transfer</button>
            </div>
            {msg && <div style={{ marginTop: 10, fontSize: 13, color: '#d8a93d' }}>{msg}</div>}
          </>
        ) : recommendationError ? (
          <div style={{ fontSize: 13, color: '#e05c5c' }}>Recommendation unavailable: {recommendationError.message}</div>
        ) : recommendationTarget ? (
          <div style={{ fontSize: 13, color: '#8b94a3' }}>
            No feasible transfer is currently recommended for work order {recommendationTarget.id} on {recommendationTarget.aircraft_id} ({recommendationTarget.required_component}).
            {rec?.rejected?.length ? <ul>{rec.rejected.map((item, i) => <li key={i}>{baseName(item.source_base || item.base_id)} — {item.reason || item.detail}</li>)}</ul> : null}
            <div style={{ marginTop: 8 }}><button onClick={() => onOpenAircraft(recommendationTarget.aircraft_id)} style={{ background: 'transparent', border: '1px solid #2a3444', color: '#e6e9ee', borderRadius: 7, padding: '7px 12px', cursor: 'pointer' }}>View aircraft</button></div>
          </div>
        ) : (
          <div style={{ fontSize: 13, color: '#8b94a3' }}>No active component work order is available for recommendation.</div>
        )}
      </div>

      <SectionTitle>Base readiness</SectionTitle>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: 12 }}>
        {(fleet?.bases || []).map(b => (
          <div key={b.id} className="ops-card" style={{ padding: 14 }}>
            <div style={{ fontWeight: 800 }}>{b.name}</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: b.availability_pct >= 85 ? '#3fb97f' : '#d8a93d' }}>{b.availability_pct}%</div>
            <div style={{ fontSize: 12, color: '#8b94a3' }}>{b.available}/{b.aircraft_count} available · {b.at_risk} at risk · {b.maintenance} mx</div>
            <BaseMissionReadiness base={b} />
          </div>
        ))}
      </div>

      <SectionTitle>Fleet risk — high-risk aircraft</SectionTitle>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: 12 }}>
        {atRisk.slice(0, 4).map(a => (
          <button key={a.id} onClick={() => onOpenAircraft(a.id)} style={{ textAlign: 'left', cursor: 'pointer', background: '#151b24', border: '1px solid #2a3444', borderRadius: 10, padding: 14, color: '#e6e9ee' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}><b>{a.id}</b><Badge color={riskColor(a.health.risk_level)}>{a.health.risk_level} RISK</Badge></div>
            <div style={{ fontSize: 12, color: '#8b94a3', marginTop: 4 }}>{baseName(a.base_id)} · RUL {rulText(a.health)} · Health {healthScoreText(a.health)}</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>Required: <b>{a.health.required_component || a.required_component || '—'}</b></div>
          </button>
        ))}
      </div>

      <SectionTitle>Transfers</SectionTitle>
      <div className="ops-card" style={{ padding: 0, overflowX: 'auto' }}>
        <table style={{ width: '100%', minWidth: 520, fontSize: 13, borderCollapse: 'collapse' }}>
          <thead><tr style={{ textAlign: 'left', color: '#8b94a3', fontSize: 11 }}>
            <th style={{ padding: 10 }}>ID</th><th>Part</th><th>Route</th><th>Status</th><th>ETA</th>
          </tr></thead>
          <tbody>
            {transfers.map(t => (
              <tr key={t.id} style={{ borderTop: '1px solid #2a3444' }}>
                <td style={{ padding: 10 }} className="font-mono">{t.id}</td><td>{t.part_number}</td>
                <td>{baseName(t.source_base)} → {baseName(t.dest_base)}</td><td>{t.status}</td><td>{etaText(t.eta_hours)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ReadinessSimulationPanel refreshKey={refreshKey} />
    </div>
  );
}
