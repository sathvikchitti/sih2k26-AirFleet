import React from 'react';
import { api } from '../services/api.js';
import { C } from '../theme.js';

const isFiniteNumber = value => typeof value === 'number' && Number.isFinite(value);

export function RiskPolicyDetails({ policy }) {
  const thresholds = policy?.health_score?.thresholds;
  const fd001 = policy?.fd001;
  const hasThresholds = Array.isArray(thresholds) && thresholds.length > 0;
  const hasFormula = typeof fd001?.health_score_formula === 'string' && fd001.health_score_formula.length > 0;
  const hasCap = isFiniteNumber(fd001?.rul_cap_cycles);
  return (
    <div style={{ fontSize: 11, color: C.text2, lineHeight: 1.5, marginTop: 7 }}>
      {hasFormula && hasCap ? <div>FD001 health score: <b>{fd001.health_score_formula}</b> · RUL cap {fd001.rul_cap_cycles} cycles.</div> : null}
      <div style={{ marginTop: 5 }}>Backend health-score risk bands{policy?.combination?.rule ? ` · combination: ${policy.combination.rule.replace(/_/g, ' ')}` : ''}:</div>
      {hasThresholds ? (
        <ul style={{ margin: '3px 0 0', paddingLeft: 18 }}>
          {thresholds.map((row, index) => (
            <li key={`${row.risk_level || 'risk'}:${index}`}>
              {row.risk_level || 'Risk'} {row.operator || '—'} {isFiniteNumber(row.value) ? row.value : 'unavailable'}
            </li>
          ))}
        </ul>
      ) : <div>Health-score threshold values unavailable.</div>}
      {policy?.configurable === true
        ? <div style={{ marginTop: 5 }}>Configurable demo policy; current values are supplied by the backend ({policy.configuration_source || 'source unavailable'}).</div>
        : <div style={{ marginTop: 5 }}>Policy configurability/source unavailable.</div>}
      {fd001?.probability_calibrated === false || fd001?.probability_status === 'unavailable'
        ? <div style={{ marginTop: 5 }}>The health score is a risk-policy indicator, not a calibrated failure probability. FD001 failure probability is unavailable.</div>
        : <div style={{ marginTop: 5 }}>The health-score bands describe policy classification; they do not provide a calibrated failure probability.</div>}
    </div>
  );
}

export default function RiskPolicyNote({ refreshKey = 0 }) {
  const [policy, setPolicy] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let active = true;
    setLoading(true);
    setPolicy(null);
    setError(null);
    api.getRiskBands()
      .then(result => { if (active) setPolicy(result); })
      .catch(err => { if (active) setError(err); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refreshKey]);

  return (
    <details style={{ marginTop: 8, color: C.muted }}>
      <summary style={{ cursor: 'pointer', fontSize: 11, color: C.warn }}>How backend risk bands are assigned</summary>
      {loading && !policy ? <div role="status" style={{ fontSize: 11, marginTop: 6 }}>Loading backend risk policy…</div> : null}
      {error ? <div role="status" style={{ fontSize: 11, color: C.crit, marginTop: 6 }}>Backend risk policy unavailable; threshold values are withheld.</div> : null}
      {policy ? <RiskPolicyDetails policy={policy} /> : null}
    </details>
  );
}
