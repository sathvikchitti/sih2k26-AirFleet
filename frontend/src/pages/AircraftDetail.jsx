import React from 'react';
import { api, baseName, distanceText, etaText, failureProbabilityText, healthScoreText, rulText } from '../services/api.js';
import { ActionButton, Badge, HealthBar, HealthChart, Loading, SectionTitle, StatusMsg, riskColor, statusColor } from '../components/ui.jsx';
import MaintenanceCasePanel from '../components/MaintenanceCasePanel.jsx';
import { Fd001ArtifactEvidence, RulEnvelope, RulHistoryChart, TopSensorDrivers } from '../components/PredictionEvidence.jsx';
import RiskPolicyNote from '../components/RiskPolicyNote.jsx';
import { C } from '../theme.js';

// Closed loop: WAITING → IN TRANSIT → RECEIVED → READY → IN_PROGRESS → AVAILABLE
export default function AircraftDetail({ id, role, homeBase, onBack, refresh, refreshKey }) {
  const [d, setD] = React.useState(null);
  const [loadError, setLoadError] = React.useState('');
  const [msg, setMsg] = React.useState('');
  const [workOrderStock, setWorkOrderStock] = React.useState(null);
  const [workOrderStockError, setWorkOrderStockError] = React.useState(null);
  const [fd001Metrics, setFd001Metrics] = React.useState(null);
  const [fd001MetricsLoading, setFd001MetricsLoading] = React.useState(false);
  const [fd001MetricsError, setFd001MetricsError] = React.useState(false);

  const load = async () => {
    setD(null);
    setLoadError('');
    try { setD(await api.getAircraftDetail(id)); }
    catch (e) { setLoadError(e?.message || 'Could not load aircraft details.'); }
  };
  React.useEffect(() => { load(); }, [id, refreshKey]);

  React.useEffect(() => {
    let active = true;
    const health = d?.health || {};
    const isFd001 = health.provider === 'fd001-random-forest'
      || String(health.source || '').startsWith('cmapss-fd001')
      || String(health.model_version || '').startsWith('cmapss-fd001');
    setFd001Metrics(null);
    setFd001MetricsError(false);
    if (!isFd001) {
      setFd001MetricsLoading(false);
      return () => { active = false; };
    }
    setFd001MetricsLoading(true);
    api.getFd001Metrics()
      .then(result => { if (active) setFd001Metrics(result); })
      .catch(() => { if (active) setFd001MetricsError(true); })
      .finally(() => { if (active) setFd001MetricsLoading(false); });
    return () => { active = false; };
  }, [id, d?.health?.model_version, d?.health?.provider, d?.health?.source, refreshKey]);

  const modelComponent = d?.health?.required_component || d?.required_component || null;
  const activeWorkOrder = d?.work_orders?.find(wo => String(wo.status || '').toUpperCase() !== 'COMPLETED') || d?.maintenance || null;
  const workOrderComponent = activeWorkOrder?.required_component || activeWorkOrder?.component || null;
  const displayComponent = workOrderComponent || modelComponent;
  const needsWorkOrderStock = Boolean(workOrderComponent && workOrderComponent !== modelComponent);

  React.useEffect(() => {
    let active = true;
    if (!needsWorkOrderStock) {
      setWorkOrderStock(null);
      setWorkOrderStockError(null);
      return () => { active = false; };
    }
    setWorkOrderStock(null);
    setWorkOrderStockError(null);
    api.getInventoryLive()
      .then(rows => { if (active) setWorkOrderStock((rows || []).filter(row => row.part_number === workOrderComponent).map(row => ({
        ...row,
        distance_km: row.distance_km ?? null,
        eta_hours: row.eta_hours ?? null,
      }))); })
      .catch(error => { if (active) setWorkOrderStockError(error); });
    return () => { active = false; };
  }, [id, d?.base_id, workOrderComponent, needsWorkOrderStock, refreshKey]);

  if (!d && loadError) return <div style={{ color: C.crit }}>Could not load {id}: {loadError}</div>;
  if (!d) return <Loading>Loading {id}…</Loading>;
  const h = d.health || {};
  const fallbackPrediction = h.model_version === 'demo-fallback';
  const rec = d.recommendation;
  const metadata = h.metadata || d.metadata || {};
  const timestamp = h.prediction_timestamp || metadata.prediction_timestamp;
  const predictionTime = timestamp ? Date.parse(timestamp) : NaN;
  const predictionStale = Number.isFinite(predictionTime) && h.prediction_horizon_hours != null
    && Date.now() > predictionTime + Number(h.prediction_horizon_hours) * 60 * 60 * 1000;
  const historySource = h.history_source || d.history_source || '';
  const trendSource = d.trend_source || h.trend_source || '';
  const fd001PrefixTrend = trendSource === 'fd001_model_prefix_predictions';
  const healthTrendCaption = fd001PrefixTrend ? 'FD001 prefix predictions'
    : trendSource === 'illustrative_mock_curve' ? 'illustrative mock curve' : 'provider trend';
  const syntheticEngineHistory = Boolean(h.is_synthetic || d.is_synthetic)
    && (String(historySource).includes('cmapss') || String(h.source || d.source || '').includes('cmapss'));

  const doAction = async (fn, label) => {
    setMsg(label + '…');
    try { await fn(); setMsg(label + ' — done'); load(); refresh(); }
    catch (e) { setMsg(e?.message || 'Action failed. Check the backend connection and try again.'); }
  };

  const mxStatus = (activeWorkOrder && activeWorkOrder.status) || '—';
  const resourceRows = needsWorkOrderStock ? workOrderStock : d.resource_availability;
  const recoveryHours = (activeWorkOrder && activeWorkOrder.estimated_recovery_hours) ?? d.estimated_recovery_hours;

  return (
    <div>
      <ActionButton small quiet onClick={onBack}>← Back</ActionButton>
      <div className="ops-page-header" style={{ marginTop: 10 }}>
        <div>
          <div className="ops-label">{baseName(d.base_id)} · {d.type}</div>
          <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap', marginTop: 10 }}>
            <h2 className="ops-page-title" style={{ fontFamily: 'var(--font-mono)', fontSize: 40, letterSpacing: '.02em' }}>{d.id}</h2>
            <Badge color={statusColor(d.status)}>{String(d.status).replace(/_/g, ' ')}</Badge>
            {h.risk_level && <Badge color={riskColor(h.risk_level)}>{h.risk_level} RISK</Badge>}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', gap: 12, marginTop: 20 }}>
        <div className="ops-card" style={{ padding: '18px 20px' }}>
          <div className="ops-label">{h.health_score_derived ? 'Health indicator derived from RUL' : 'Health prediction'} · {fallbackPrediction ? 'offline fallback' : 'aircraft detail API snapshot'}</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, margin: '12px 0 10px' }}><span style={{ fontFamily: 'var(--font-display)', fontSize: 64, fontWeight: 700, lineHeight: .9, color: riskColor(h.risk_level) }}>{healthScoreText(h)}</span><span style={{ fontSize: 13, color: C.muted }}>health</span></div>
          {h.health_score != null && <HealthBar score={h.health_score} />}
          <div className="ops-kv">
            <div>Failure probability<br /><b>{failureProbabilityText(h)}</b></div>
            <div>Remaining useful life<br /><b>{rulText(h)}</b></div>
            <div>Uncalibrated model spread<br /><b><RulEnvelope prediction={h} /></b></div>
            <div>Confidence<br /><b>{failureProbabilityText({ failure_probability: h.confidence })}</b></div>
            <div>Predicted mx<br /><b>{h.predicted_maintenance == null ? 'Unavailable' : h.predicted_maintenance ? 'REQUIRED' : 'Not required'}</b></div>
            <div>Subsystem<br /><b>{h.subsystem || 'Unavailable'}</b></div>
          </div>
          {h.probability_status === 'unavailable' && <div style={{ marginTop: 6, fontSize: 11, color: C.muted }}>Risk band follows the backend health-only policy; it is not a calibrated failure probability.</div>}
          <RiskPolicyNote refreshKey={refreshKey} />
          {(h.model_version || h.prediction_timestamp || metadata.prediction_timestamp || h.prediction_horizon_hours != null || h.is_synthetic || h.history_source || h.source || h.provider || fallbackPrediction) && (
            <div style={{ marginTop: 10, fontSize: 11, color: C.muted }}>
              {fallbackPrediction ? 'OFFLINE DEMO FALLBACK · illustrative prediction, not live' : h.model_version ? <>Model {h.model_version}</> : 'Prediction provenance unavailable'}
              {h.provider ? <> · Provider {h.provider}</> : null}
              {h.source ? <> · Source {h.source}</> : null}
              {h.health_score_derived ? <> · Method {String(h.health_score_derived).replace(/_/g, ' ')}</> : null}
              {timestamp ? <> · As of {new Date(timestamp).toLocaleString()}</> : null}
              {h.prediction_horizon_hours != null ? <> · {h.prediction_horizon_hours}h horizon</> : null}
              {metadata.engine_id != null ? <> · NASA engine {metadata.engine_id}</> : null}
              {metadata.observation_cycle_count != null ? <> · {metadata.observation_cycle_count} observed cycles</> : null}
              {syntheticEngineHistory ? <> · Synthetic NASA FD001 history mapped to demo aircraft</> : null}
              {!syntheticEngineHistory && (h.is_synthetic || d.is_synthetic || historySource === 'illustrative') ? <> · Illustrative prediction history</> : null}
              {predictionStale || h.is_stale ? <> · <b style={{ color: C.crit }}>Stale prediction</b></> : null}
            </div>
          )}
          <TopSensorDrivers drivers={h.top_drivers} method={h.driver_method} />
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: `1px solid ${C.line}`, fontSize: 13, lineHeight: 1.7 }}>ML required component: <b>{modelComponent || '—'}</b></div>
          {workOrderComponent && <div style={{ fontSize: 13, lineHeight: 1.7 }}>Active work-order component: <b>{workOrderComponent}</b>{activeWorkOrder?.component_source === 'human_selected' ? <span style={{ color: C.muted }}> · selected by operator, not an ML output</span> : activeWorkOrder?.component_source === 'knowledge_rule' ? <span style={{ color: C.muted }}> · selected by maintenance rule</span> : null}</div>}
          <div style={{ fontSize: 13, lineHeight: 1.7 }}>Maintenance priority: <b>{(activeWorkOrder && activeWorkOrder.priority) || d.priority || 'Unavailable'}</b> · Est. recovery <b>{recoveryHours == null ? 'Unavailable' : `${recoveryHours}h`}</b></div>
          <div style={{ fontSize: 13, lineHeight: 1.7 }}>Maintenance status: <b>{mxStatus}</b></div>
        </div>
        <div className="ops-card" style={{ padding: '18px 20px' }}>
          <div className="ops-label">Health trend ({fd001PrefixTrend ? 'FD001 model predictions over synthetic engine history' : trendSource === 'illustrative_mock_curve' ? 'illustrative mock curve' : historySource === 'recorded' ? 'recorded' : 'illustrative'})</div>
          <div style={{ marginTop: 12 }}><HealthChart trend={d.trend} caption={healthTrendCaption} /></div>
          <div style={{ marginTop: 12 }}><RulHistoryChart trend={d.rul_trend} /></div>
          {fd001PrefixTrend || h.provider === 'fd001-random-forest' || String(h.source || '').startsWith('cmapss-fd001') ? (
            <Fd001ArtifactEvidence
              metrics={fd001Metrics}
              selectedModelVersion={h.model_version}
              trendModelVersion={d.rul_trend_model_version}
              loading={fd001MetricsLoading}
              error={fd001MetricsError}
            />
          ) : null}
          <div style={{ fontSize: 11, color: C.dim, marginTop: 6 }}>
            {fd001PrefixTrend ? 'Retrospective Random Forest predictions over simulated NASA C-MAPSS FD001 test-engine prefixes mapped to this demo aircraft; not real aircraft telemetry.' : trendSource === 'illustrative_mock_curve' || d.is_synthetic || historySource !== 'recorded' ? 'Illustrative degradation trend — not raw sensor data.' : 'Recorded prediction history — not raw sensor data.'}
          </div>
        </div>
      </div>

      <SectionTitle>Resource availability — {displayComponent || 'no component selected'}</SectionTitle>
      <div className="ops-card ops-table-scroll">
        {!displayComponent ? <div style={{ padding: 12, color: C.muted, fontSize: 12 }}>No model component or active work-order component is selected; there are no component stock locations to display.</div> : <>
          {needsWorkOrderStock && workOrderStockError ? <div style={{ padding: 12, color: C.crit, fontSize: 12 }}>Stock locations for the work-order component are unavailable. {workOrderStockError.message}</div> : null}
          {needsWorkOrderStock && !workOrderStock && !workOrderStockError ? <div style={{ padding: 12, color: C.muted, fontSize: 12 }}>Loading stock locations for {workOrderComponent}…</div> : null}
          <table className="ops-table" style={{ minWidth: 560 }}>
            <thead><tr>
              <th>Base</th><th>Qty</th><th>Condition</th><th>Distance</th><th>ETA</th><th>Status</th>
            </tr></thead>
            <tbody>
              {(resourceRows || []).map((r, i) => (
                <tr key={i} className="ops-table-row">
                  <td>{baseName(r.base_id)}</td><td className="ops-number">{r.quantity}</td>
                  <td>{r.condition_pct == null ? '—' : `${r.condition_pct}%`}</td><td>{distanceText(r.distance_km)}</td><td>{etaText(r.eta_hours)}</td><td>{r.status ? <Badge color={statusColor(r.status)}>{String(r.status).replace(/_/g, ' ')}</Badge> : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {resourceRows && resourceRows.length === 0 ? <div style={{ padding: 10, color: C.muted, fontSize: 12 }}>No inventory rows found for {displayComponent}.</div> : null}
        </>}
      </div>

      {rec?.recommended && (
        <>
          <SectionTitle>Recommended sourcing</SectionTitle>
          <div className="ops-card ops-callout" style={{ '--callout': C.warn }}>
            <div className="ops-label" style={{ color: C.warn }}>Recommended action</div>
            <div className="ops-action-route" style={{ fontSize: 16 }}>Transfer <b>{rec.required_component}</b> from <b>{baseName(rec.recommended.donor_base)}</b><span className="ops-action-eta">ETA {rec.recommended.eta_hours}h</span></div>
            <ul className="ops-reasons">
              {rec.recommended.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
            <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
              <ActionButton primary onClick={() => doAction(() => api.approveRecommendation(d.id), 'Approving transfer')}>Approve Transfer</ActionButton>
              <ActionButton onClick={() => doAction(() => api.startMx(d.id), 'Starting maintenance')}>Start Maintenance</ActionButton>
              <ActionButton onClick={() => doAction(() => api.completeMx(d.id), 'Completing work order; aircraft status will be recomputed')}>Complete Work Order</ActionButton>
            </div>
            <StatusMsg>{msg}</StatusMsg>
            <div className="ops-note" style={{ marginTop: 12 }}>
              Workflow: approve → IN TRANSIT → (Logistics: simulate arrival → RECEIVED) → start → complete work order; aircraft availability is recomputed from the current classifier and prediction.
            </div>
          </div>
        </>
      )}
      <MaintenanceCasePanel aircraftId={d.id} baseId={d.base_id} role={role} homeBase={homeBase} refresh={refresh} refreshKey={refreshKey} />
    </div>
  );
}
