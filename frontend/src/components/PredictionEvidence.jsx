import React from 'react';
import { rulText } from '../services/api.js';

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

export function RulHistoryChart({ trend }) {
  const points = (Array.isArray(trend) ? trend : [])
    .filter(point => finite(point?.cycle) && finite(point?.rul_cycles));
  if (points.length === 0) {
    return <div style={{ color: '#8b94a3', fontSize: 12, padding: 10 }}>RUL history unavailable for this provider.</div>;
  }

  const yValues = points.flatMap(point => [
    Number(point.rul_cycles),
    ...(finite(point.rul_low) && finite(point.rul_high) && Number(point.rul_low) <= Number(point.rul_high)
      ? [Number(point.rul_low), Number(point.rul_high)] : []),
  ]);
  let minCycle = Math.min(...points.map(point => Number(point.cycle)));
  let maxCycle = Math.max(...points.map(point => Number(point.cycle)));
  let minRul = Math.min(...yValues);
  let maxRul = Math.max(...yValues);
  if (minCycle === maxCycle) { minCycle -= 0.5; maxCycle += 0.5; }
  if (minRul === maxRul) { minRul -= 0.5; maxRul += 0.5; }

  const width = 460, height = 150, left = 48, right = 12, top = 10, bottom = 27;
  const x = cycle => left + ((Number(cycle) - minCycle) / (maxCycle - minCycle)) * (width - left - right);
  const y = value => height - bottom - ((Number(value) - minRul) / (maxRul - minRul)) * (height - top - bottom);
  const chartPoints = points.map(point => ({
    ...point,
    x: x(point.cycle),
    y: y(point.rul_cycles),
    yLow: finite(point.rul_low) && finite(point.rul_high) && Number(point.rul_low) <= Number(point.rul_high) ? y(point.rul_low) : null,
    yHigh: finite(point.rul_low) && finite(point.rul_high) && Number(point.rul_low) <= Number(point.rul_high) ? y(point.rul_high) : null,
  }));
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

  return (
    <div>
      <div style={{ color: '#8b94a3', fontSize: 11, margin: '4px 0 6px' }}>
        RUL history (cycles) · {intervalAvailable ? 'tree-spread envelope, uncalibrated' : 'interval unavailable'}
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="RUL estimates across observed cycles, measured in cycles" style={{ width: '100%', height: 160, background: '#0a0e13', border: '1px solid #2a3444', borderRadius: 8 }}>
        <line x1={left} y1={height - bottom} x2={width - right} y2={height - bottom} stroke="#2a3444" />
        <line x1={left} y1={top} x2={left} y2={height - bottom} stroke="#2a3444" />
        <text x={left - 6} y={top + 4} textAnchor="end" fill="#8b94a3" fontSize="9">{cycleText(maxRul)}</text>
        <text x={left - 6} y={height - bottom + 3} textAnchor="end" fill="#8b94a3" fontSize="9">{cycleText(minRul)}</text>
        <text x={left} y={height - 8} fill="#8b94a3" fontSize="9">Cycle {cycleText(minCycle)}</text>
        <text x={width - right} y={height - 8} textAnchor="end" fill="#8b94a3" fontSize="9">Cycle {cycleText(maxCycle)}</text>
        {intervalSegments.map((items, index) => items.length > 1 ? (
          <path key={`band-${index}`} d={`${pathFor(items, 'yHigh')} ${items.slice().reverse().map(point => `L${point.x.toFixed(1)} ${point.yLow.toFixed(1)}`).join(' ')} Z`} fill="#4f9cf0" opacity="0.2">
            <title>Mean-inclusive envelope around the raw 10th–90th percentile tree spread; uncalibrated.</title>
          </path>
        ) : (
          <line key={`band-${index}`} x1={items[0].x} x2={items[0].x} y1={items[0].yHigh} y2={items[0].yLow} stroke="#4f9cf0" strokeWidth="5" opacity="0.4" />
        ))}
        <path d={pathFor(chartPoints, 'y')} fill="none" stroke="#d8a93d" strokeWidth="2.5" />
        {chartPoints.map((point, index) => <circle key={`${point.cycle}-${index}`} cx={point.x} cy={point.y} r="2.8" fill="#d8a93d" />)}
      </svg>
      <div style={{ fontSize: 11, color: '#c6ccd6', marginTop: 4 }}>
        Latest prefix estimate: <b>{cycleText(points[points.length - 1].rul_cycles)} cycles</b>
      </div>
      <div style={{ fontSize: 10, color: '#8b94a3', marginTop: 5 }}>
        {intervalAvailable
          ? 'Band is the mean-inclusive envelope around raw 10th–90th percentile tree spread; it is uncalibrated, not a confidence interval.'
          : 'RUL estimates are shown without an interval because this provider does not supply tree-spread bounds.'}
      </div>
    </div>
  );
}

export function TopSensorDrivers({ drivers, method }) {
  const items = Array.isArray(drivers) ? drivers.slice(0, 5) : [];
  return (
    <div style={{ marginTop: 12 }}>
      <div className="ops-label">Top sensor / setting drivers · indicative</div>
      <div title={method || undefined} style={{ fontSize: 10, lineHeight: 1.5, color: '#8b94a3', margin: '4px 0 7px' }}>
        Importance-weighted deviations from the model's capped high-RUL training-prefix reference; indicative only, not causal attribution or failure probability.
      </div>
      {items.length === 0 ? (
        <div style={{ color: '#8b94a3', fontSize: 11 }}>Sensor drivers unavailable for this provider.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {items.map((driver, index) => {
            const sensor = driver.sensor || driver.sensor_name || driver.feature || driver.feature_name || 'Sensor unavailable';
            const feature = driver.statistic ? `${sensor} · ${driver.statistic}` : sensor;
            const direction = driver.direction === 'below_reference' ? 'Below training reference'
              : driver.direction === 'above_reference' ? 'Above training reference'
                : String(driver.direction || 'Direction unavailable').replace(/_/g, ' ');
            const score = finite(driver.contribution_score) ? Number(driver.contribution_score) : null;
            const scoreText = score == null ? '—' : `${score > 0 ? '+' : ''}${score.toFixed(3)}`;
            return (
              <div key={`${driver.feature || driver.feature_name || sensor}-${index}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 11 }}>
                <span><b>{feature}</b> · {direction}</span>
                <span style={{ color: '#c6ccd6', whiteSpace: 'nowrap' }}>{scoreText}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
