import React from 'react';
import { api, baseName, distanceText, etaText, failureProbabilityText, healthScoreText, rulText } from '../services/api.js';
import { Badge, HealthBar, HealthChart, SectionTitle, riskColor, statusColor } from '../components/ui.jsx';
import MaintenanceCasePanel from '../components/MaintenanceCasePanel.jsx';
import { Fd001ArtifactEvidence, RulEnvelope, RulHistoryChart, TopSensorDrivers } from '../components/PredictionEvidence.jsx';
import RiskPolicyNote from '../components/RiskPolicyNote.jsx';

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

  if (!d && loadError) return <div style={{ color: '#e05c5c' }}>Could not load {id}: {loadError}</div>;
  if (!d) return <div style={{ color: '#8b94a3' }}>Loading {id}…</div>;
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
      <button onClick={onBack} style={{ background: 'transparent', border: 'none', color: '#8b94a3', cursor: 'pointer', fontSize: 13 }}>← Back</button>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 6 }}>
        <h2 style={{ fontSize: 24, fontWeight: 800 }}>{d.id}</h2>
        <Badge color={statusColor(d.status)}>{d.status.replace('_', ' ')}</Badge>
        {h.risk_level && <Badge color={riskColor(h.risk_level)}>{h.risk_level} RISK</Badge>}
        <span style={{ fontSize: 12, color: '#8b94a3' }}>{baseName(d.base_id)} · {d.type}</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 12, marginTop: 14 }}>
        <div className="ops-card" style={{ padding: 16 }}>
          <div className="ops-label">{h.health_score_derived ? 'Health indicator derived from RUL' : 'Health prediction'} · {fallbackPrediction ? 'offline fallback' : 'aircraft detail API snapshot'}</div>
          <div style={{ fontSize: 34, fontWeight: 800, color: riskColor(h.risk_level) }}>{healthScoreText(h)} <span style={{ fontSize: 13, color: '#8b94a3', fontWeight: 400 }}>health</span></div>
          {h.health_score != null && <HealthBar score={h.health_score} />}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 12, fontSize: 13 }}>
            <div>Failure probability<br /><b>{failureProbabilityText(h)}</b></div>
            <div>Remaining useful life<br /><b>{rulText(h)}</b></div>
            <div>Uncalibrated model spread<br /><b><RulEnvelope prediction={h} /></b></div>
            <div>Confidence<br /><b>{failureProbabilityText({ failure_probability: h.confidence })}</b></div>
            <div>Predicted mx<br /><b>{h.predicted_maintenance == null ? 'Unavailable' : h.predicted_maintenance ? 'REQUIRED' : 'Not required'}</b></div>
            <div>Subsystem<br /><b>{h.subsystem || 'Unavailable'}</b></div>
          </div>
          {h.probability_status === 'unavailable' && <div style={{ marginTop: 6, fontSize: 11, color: '#8b94a3' }}>Risk band follows the backend health-only policy; it is not a calibrated failure probability.</div>}
          <RiskPolicyNote refreshKey={refreshKey} />
          {(h.model_version || h.prediction_timestamp || metadata.prediction_timestamp || h.prediction_horizon_hours != null || h.is_synthetic || h.history_source || h.source || h.provider || fallbackPrediction) && (
            <div style={{ marginTop: 10, fontSize: 11, color: '#8b94a3' }}>
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
              {predictionStale || h.is_stale ? <> · <b style={{ color: '#e05c5c' }}>Stale prediction</b></> : null}
            </div>
          )}
          <TopSensorDrivers drivers={h.top_drivers} method={h.driver_method} />
          <div style={{ marginTop: 10, fontSize: 13 }}>ML required component: <b>{modelComponent || '—'}</b></div>
          {workOrderComponent && <div style={{ fontSize: 13 }}>Active work-order component: <b>{workOrderComponent}</b>{activeWorkOrder?.component_source === 'human_selected' ? <span style={{ color: '#8b94a3' }}> · selected by operator, not an ML output</span> : activeWorkOrder?.component_source === 'knowledge_rule' ? <span style={{ color: '#8b94a3' }}> · selected by maintenance rule</span> : null}</div>}
          <div style={{ fontSize: 13 }}>Maintenance priority: <b>{(activeWorkOrder && activeWorkOrder.priority) || d.priority || 'Unavailable'}</b> · Est. recovery <b>{recoveryHours == null ? 'Unavailable' : `${recoveryHours}h`}</b></div>
          <div style={{ fontSize: 13 }}>Maintenance status: <b>{mxStatus}</b></div>
        </div>
        <div className="ops-card" style={{ padding: 16 }}>
          <div className="ops-label">Health trend ({fd001PrefixTrend ? 'FD001 model predictions over synthetic engine history' : trendSource === 'illustrative_mock_curve' ? 'illustrative mock curve' : historySource === 'recorded' ? 'recorded' : 'illustrative'})</div>
          <div style={{ marginTop: 8 }}><HealthChart trend={d.trend} caption={healthTrendCaption} /></div>
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
          <div style={{ fontSize: 11, color: '#5d6675', marginTop: 6 }}>
            {fd001PrefixTrend ? 'Retrospective Random Forest predictions over simulated NASA C-MAPSS FD001 test-engine prefixes mapped to this demo aircraft; not real aircraft telemetry.' : trendSource === 'illustrative_mock_curve' || d.is_synthetic || historySource !== 'recorded' ? 'Illustrative degradation trend — not raw sensor data.' : 'Recorded prediction history — not raw sensor data.'}
          </div>
        </div>
      </div>

      <SectionTitle>Resource availability — {displayComponent || 'no component selected'}</SectionTitle>
      <div className="ops-card" style={{ overflow: 'hidden' }}>
        {!displayComponent ? <div style={{ padding: 12, color: '#8b94a3', fontSize: 12 }}>No model component or active work-order component is selected; there are no component stock locations to display.</div> : <>
          {needsWorkOrderStock && workOrderStockError ? <div style={{ padding: 12, color: '#e05c5c', fontSize: 12 }}>Stock locations for the work-order component are unavailable. {workOrderStockError.message}</div> : null}
          {needsWorkOrderStock && !workOrderStock && !workOrderStockError ? <div style={{ padding: 12, color: '#8b94a3', fontSize: 12 }}>Loading stock locations for {workOrderComponent}…</div> : null}
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <thead><tr style={{ textAlign: 'left', color: '#8b94a3', fontSize: 11 }}>
              <th style={{ padding: 10 }}>Base</th><th>Qty</th><th>Condition</th><th>Distance</th><th>ETA</th><th>Status</th>
            </tr></thead>
            <tbody>
              {(resourceRows || []).map((r, i) => (
                <tr key={i} style={{ borderTop: '1px solid #2a3444' }}>
                  <td style={{ padding: 10 }}>{baseName(r.base_id)}</td><td>{r.quantity}</td>
                  <td>{r.condition_pct == null ? '—' : `${r.condition_pct}%`}</td><td>{distanceText(r.distance_km)}</td><td>{etaText(r.eta_hours)}</td><td>{r.status || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {resourceRows && resourceRows.length === 0 ? <div style={{ padding: 10, color: '#8b94a3', fontSize: 12 }}>No inventory rows found for {displayComponent}.</div> : null}
        </>}
      </div>

      {rec?.recommended && (
        <>
          <SectionTitle>Recommended sourcing</SectionTitle>
          <div className="ops-card" style={{ padding: 16, borderLeft: '4px solid #d8a93d' }}>
            <div className="ops-label">Recommended action</div>
            <div style={{ fontSize: 17, fontWeight: 800, marginTop: 4 }}>Transfer {rec.required_component} from {baseName(rec.recommended.donor_base)} — ETA {rec.recommended.eta_hours}h</div>
            <ul style={{ fontSize: 13, color: '#c6ccd6', paddingLeft: 18, marginTop: 8 }}>
              {rec.recommended.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
            <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
              <button onClick={() => doAction(() => api.approveRecommendation(d.id), 'Approving transfer')} style={primaryBtn}>Approve Transfer</button>
              <button onClick={() => doAction(() => api.startMx(d.id), 'Starting maintenance')} style={btn}>Start Maintenance</button>
              <button onClick={() => doAction(() => api.completeMx(d.id), 'Completing work order; aircraft status will be recomputed')} style={btn}>Complete Work Order</button>
            </div>
            {msg && <div style={{ marginTop: 8, fontSize: 13, color: '#d8a93d' }}>{msg}</div>}
            <div style={{ fontSize: 12, color: '#8b94a3', marginTop: 8 }}>
              Workflow: approve → IN TRANSIT → (Logistics: simulate arrival → RECEIVED) → start → complete work order; aircraft availability is recomputed from the current classifier and prediction.
            </div>
          </div>
        </>
      )}
      <MaintenanceCasePanel aircraftId={d.id} baseId={d.base_id} role={role} homeBase={homeBase} refresh={refresh} refreshKey={refreshKey} />
    </div>
  );
}

const btn = { background: '#1c2431', border: '1px solid #2a3444', color: '#e6e9ee', borderRadius: 7, padding: '8px 14px', cursor: 'pointer' };
const primaryBtn = { background: '#d8a93d', border: 'none', color: '#111', fontWeight: 800, borderRadius: 7, padding: '8px 14px', cursor: 'pointer' };
