import React from 'react';
import { rulText } from '../services/api.js';
import { C, CAT } from '../theme.js';
import { AXIS_FONT, ChartTooltip, TipRow, niceTicks, useMeasuredWidth, useNearestIndex } from './charts.jsx';

const finite = value => value != null && value !== '' && Number.isFinite(Number(value));
const cycleText = value => Number(value).toFixed(2).replace(/\.00$/, '');

export function RulEnvelope({ prediction }) {
  const low = prediction?.rul_low;
  const high = prediction?.rul_high;
  if (low == null || high == null || !finite(low) || !finite(high) || Number(low) > Number(high)) {
    return 'Unavailable';
  }
  return `${rulText({ rul: low, rul_unit: prediction.rul_unit })} – ${rulText({ rul: high, rul_unit: prediction.rul_unit })}`;
}

function pathFor(points, key) {
  return points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(1)} ${point[key].toFixed(1)}`).join(' ');
}

// Estimate line uses the deeper chart blue; the lighter token blue is kept
// for the spread band only, so the two never read as the same mark.
const LINE = CAT[1];

export function RulHistoryChart({ trend }) {
  const points = (Array.isArray(trend) ? trend : [])
    .filter(point => finite(point?.cycle) && finite(point?.rul_cycles));
  const hasBand = point => finite(point.rul_low) && finite(point.rul_high) && Number(point.rul_low) <= Number(point.rul_high);

  const yValues = points.flatMap(point => [Number(point.rul_cycles), ...(hasBand(point) ? [Number(point.rul_low), Number(point.rul_high)] : [])]);
  let minCycle = points.length ? Math.min(...points.map(point => Number(point.cycle))) : 0;
  let maxCycle = points.length ? Math.max(...points.map(point => Number(point.cycle))) : 1;
  let minRul = yValues.length ? Math.min(...yValues) : 0;
  let maxRul = yValues.length ? Math.max(...yValues) : 1;
  if (minCycle === maxCycle) { minCycle -= 0.5; maxCycle += 0.5; }
  if (minRul === maxRul) { minRul -= 0.5; maxRul += 0.5; }
  const yTicks = niceTicks(Math.max(0, minRul), maxRul, 4);
  const yMin = Math.min(minRul, yTicks[0] ?? minRul);
  const yMax = Math.max(maxRul, yTicks[yTicks.length - 1] ?? maxRul);

  const [frameRef, measured] = useMeasuredWidth(520);
  const width = Math.max(280, measured), height = 200, left = 44, right = 56, top = 12, bottom = 28;
  const x = cycle => left + ((Number(cycle) - minCycle) / (maxCycle - minCycle)) * (width - left - right);
  const y = value => height - bottom - ((Number(value) - yMin) / (yMax - yMin || 1)) * (height - top - bottom);
  const chartPoints = points.map(point => ({
    ...point,
    x: x(point.cycle),
    y: y(point.rul_cycles),
    yLow: hasBand(point) ? y(point.rul_low) : null,
    yHigh: hasBand(point) ? y(point.rul_high) : null,
  }));
  const [hover, onMove, onLeave] = useNearestIndex(chartPoints.map(p => p.x), width);
  if (points.length === 0) {
    return <div style={{ color: C.muted, fontSize: 12, padding: 10 }}>RUL history unavailable for this provider.</div>;
  }
  const intervalSegments = [];
  let segment = [];
  for (const point of chartPoints) {
    if (point.yLow == null || point.yHigh == null) {
      if (segment.length) intervalSegments.push(segment);
      segment = [];
    } else {
      segment.push(point);
    }
  }
  if (segment.length) intervalSegments.push(segment);
  const intervalAvailable = chartPoints.some(point => point.yLow != null && point.yHigh != null);
  const last = chartPoints[chartPoints.length - 1];
  const hp = hover != null ? chartPoints[hover] : null;

  return (
    <div>
      <div className="ops-chart-head">
        <span className="ops-label">RUL history (cycles) · {intervalAvailable ? 'uncalibrated model spread' : 'interval unavailable'}</span>
        <span className="ops-legend">
          <span className="ops-legend-item"><span className="ops-swatch is-line" style={{ background: LINE }} />Estimate</span>
          {intervalAvailable ? <span className="ops-legend-item"><span className="ops-swatch" style={{ background: C.info, opacity: 0.35 }} />Spread</span> : null}
        </span>
      </div>
      <div className="ops-chart-frame" ref={frameRef}>
        <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label="RUL estimates across observed cycles, measured in cycles" className="ops-chart-svg ops-chart-well">
          {yTicks.map(t => (
            <g key={t}>
              <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} stroke={C.line} />
              <text x={left - 8} y={y(t) + 3} textAnchor="end" fill={C.muted} {...AXIS_FONT}>{cycleText(t)}</text>
            </g>
          ))}
          <text x={left} y={height - 8} fill={C.muted} {...AXIS_FONT}>Cycle {cycleText(minCycle)}</text>
          <text x={width - right} y={height - 8} textAnchor="end" fill={C.muted} {...AXIS_FONT}>Cycle {cycleText(maxCycle)}</text>
          {intervalSegments.map((items, index) => items.length > 1 ? (
            <path key={`band-${index}`} d={`${pathFor(items, 'yHigh')} ${items.slice().reverse().map(point => `L${point.x.toFixed(1)} ${point.yLow.toFixed(1)}`).join(' ')} Z`} fill={C.info} opacity="0.18">
              <title>Uncalibrated model spread: mean-inclusive envelope around the raw 10th–90th percentile tree spread.</title>
            </path>
          ) : (
            <line key={`band-${index}`} x1={items[0].x} x2={items[0].x} y1={items[0].yHigh} y2={items[0].yLow} stroke={C.info} strokeWidth="6" strokeLinecap="round" opacity="0.35" />
          ))}
          <path d={pathFor(chartPoints, 'y')} fill="none" stroke={LINE} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
          <circle cx={last.x} cy={last.y} r="4.5" fill={LINE} stroke={C.deck} strokeWidth="2" />
          <text x={last.x + 10} y={last.y + 4} fill={C.text} fontFamily="var(--font-mono)" fontSize="12" fontWeight="700">{cycleText(last.rul_cycles)}</text>
          {hp && (
            <g pointerEvents="none">
              <line x1={hp.x} x2={hp.x} y1={top} y2={height - bottom} stroke={C.text2} />
              <circle cx={hp.x} cy={hp.y} r="4.5" fill={LINE} stroke={C.deck} strokeWidth="2" />
            </g>
          )}
          <rect x={left} y={top} width={width - left - right} height={height - top - bottom} fill="transparent" onMouseMove={onMove} onMouseLeave={onLeave} />
        </svg>
        {hp && (
          <ChartTooltip xPct={(hp.x / width) * 100}>
            <div className="ops-chart-tip-title">Cycle {cycleText(hp.cycle)}</div>
            <TipRow color={LINE} label="RUL estimate" value={`${cycleText(hp.rul_cycles)} cycles`} />
            {hasBand(hp) ? <TipRow label="Spread" value={`${cycleText(hp.rul_low)}–${cycleText(hp.rul_high)}`} /> : null}
          </ChartTooltip>
        )}
      </div>
      <div style={{ fontSize: 11.5, color: C.text2, marginTop: 8 }}>
        Latest prefix estimate: <b>{cycleText(points[points.length - 1].rul_cycles)} cycles</b>
      </div>
      <div style={{ fontSize: 10.5, color: C.muted, marginTop: 5 }}>
        {intervalAvailable
          ? 'Uncalibrated model spread: a mean-inclusive envelope around raw 10th–90th percentile tree spread, not a confidence interval.'
          : 'RUL estimates are shown without an interval because this provider does not supply tree-spread bounds.'}
      </div>
    </div>
  );
}

const metricText = (value, digits = 2) => value != null && Number.isFinite(Number(value))
  ? Number(value).toFixed(digits) : 'Unavailable';

export function Fd001ArtifactEvidence({ metrics, selectedModelVersion, trendModelVersion, loading = false, error = null }) {
  if (loading) return <div role="status" style={{ color: C.muted, fontSize: 12 }}>Loading saved FD001 artifact evaluation…</div>;
  if (error) return <div role="status" style={{ color: C.muted, fontSize: 12 }}>Saved FD001 artifact evaluation unavailable.</div>;
  if (!metrics || metrics.status !== 'available' || !metrics.model?.version || !metrics.official_test) {
    return <div role="status" style={{ color: C.muted, fontSize: 12 }}>Saved FD001 artifact evaluation unavailable.</div>;
  }
  if (!selectedModelVersion || metrics.model.version !== selectedModelVersion) {
    return <div role="status" style={{ color: C.muted, fontSize: 12 }}>Saved artifact metrics withheld: artifact version does not match the selected prediction.</div>;
  }

  const official = metrics.official_test;
  const historyMatches = Boolean(trendModelVersion && trendModelVersion === metrics.model.version);
  const envelope = official.uncertainty?.mean_inclusive_envelope;
  const raw = official.uncertainty?.raw_tree_p10_p90;
  const observedCoverage = row => row?.observed_coverage != null && Number.isFinite(Number(row.observed_coverage))
    ? `${(Number(row.observed_coverage) * 100).toFixed(1)}% observed` : 'Unavailable';
  const rawNominal = raw?.nominal_coverage != null && Number.isFinite(Number(raw.nominal_coverage))
    ? ` / ${(Number(raw.nominal_coverage) * 100).toFixed(1)}% nominal` : '';

  return (
    <div style={{ marginTop: 12, padding: 10, border: `1px solid ${C.line}`, borderRadius: 2, fontSize: 11, color: C.text2 }}>
      <div className="ops-label">Saved FD001 artifact · official test evaluation</div>
      <div style={{ color: C.muted, marginTop: 4 }}>{metrics.dataset || 'Dataset unavailable'} · {official.engine_count ?? '—'} test engines · {metrics.unit || 'unit unavailable'}</div>
      <div style={{ marginTop: 6, overflowWrap: 'anywhere' }}>Model <b>{metrics.model.version}</b> · artifact SHA-256 <code>{metrics.model.artifact_sha256 || 'unavailable'}</code></div>
      {official.protocol ? <div style={{ color: C.muted, marginTop: 4 }}>Protocol: {official.protocol}</div> : null}
      <div style={{ marginTop: 4 }}>MAE {metricText(official.metrics?.mae_cycles)} cycles · RMSE {metricText(official.metrics?.rmse_cycles)} cycles · NASA asymmetric score {metricText(official.metrics?.nasa_asymmetric_score, 1)}</div>
      <div style={{ marginTop: 6 }}>
        Uncalibrated model spread — raw 10th–90th tree range: {observedCoverage(raw)}{rawNominal}; mean-inclusive envelope: {observedCoverage(envelope)} (reference p10–p90; nominal coverage not specified).
      </div>
      <div style={{ color: C.muted, marginTop: 4 }}>
        {historyMatches
          ? 'The saved artifact version matches both the selected prediction and prefix-history model.'
          : trendModelVersion
            ? `Prefix-history model ${trendModelVersion} does not match this artifact; historical spread coverage is withheld.`
            : 'Prefix-history model version unavailable; historical spread coverage is withheld.'}
      </div>
      {metrics.scope?.dataset_source_note ? <div style={{ color: C.muted, marginTop: 4 }}>{metrics.scope.dataset_source_note}</div> : null}
      <div style={{ color: C.muted, marginTop: 4 }}>Offline saved-artifact evaluation; uncertainty coverage is not calibrated.</div>
    </div>
  );
}

export function TopSensorDrivers({ drivers, method }) {
  const items = Array.isArray(drivers) ? drivers.slice(0, 5) : [];
  const maxAbs = Math.max(1e-9, ...items.map(d => Math.abs(Number(d.contribution_score)) || 0));
  return (
    <div style={{ marginTop: 12 }}>
      <div className="ops-label">Top sensor / setting drivers · indicative</div>
      <div title={method || undefined} style={{ fontSize: 10, lineHeight: 1.5, color: C.muted, margin: '4px 0 7px' }}>
        Importance-weighted deviations from the model's capped high-RUL training-prefix reference; indicative only, not causal attribution or failure probability.
      </div>
      {items.length === 0 ? (
        <div style={{ color: C.muted, fontSize: 11 }}>Sensor drivers unavailable for this provider.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div className="ops-legend" style={{ fontSize: 10.5 }}>
            <span className="ops-legend-item"><span className="ops-swatch" style={{ background: CAT[1] }} />Below reference</span>
            <span className="ops-legend-item"><span className="ops-swatch" style={{ background: CAT[2] }} />Above reference</span>
          </div>
          {items.map((driver, index) => {
            const sensor = driver.sensor || driver.sensor_name || driver.feature || driver.feature_name || 'Sensor unavailable';
            const feature = driver.statistic ? `${sensor} · ${driver.statistic}` : sensor;
            const direction = driver.direction === 'below_reference' ? 'Below training reference'
              : driver.direction === 'above_reference' ? 'Above training reference'
                : String(driver.direction || 'Direction unavailable').replace(/_/g, ' ');
            const score = finite(driver.contribution_score) ? Number(driver.contribution_score) : null;
            const scoreText = score == null ? '—' : `${score > 0 ? '+' : ''}${score.toFixed(3)}`;
            const width = score == null ? 0 : Math.min(50, (Math.abs(score) / maxAbs) * 50);
            const below = score != null && score < 0;
            return (
              <div key={`${driver.feature || driver.feature_name || sensor}-${index}`} className="ops-driver-row">
                <span className="ops-driver-label"><b>{feature}</b> · {direction}</span>
                <span className="ops-driver-track" aria-hidden="true">
                  <span className="ops-driver-axis" />
                  {score != null && <span className="ops-driver-bar" style={{ width: `${width}%`, [below ? 'right' : 'left']: '50%', background: below ? CAT[1] : CAT[2], borderRadius: below ? '2px 0 0 2px' : '0 2px 2px 0' }} />}
                </span>
                <span className="ops-driver-value">{scoreText}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
