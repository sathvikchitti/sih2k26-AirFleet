import React from 'react';
import { C } from '../theme.js';

// Small declarative flowchart renderer (inline SVG, no libraries).
//
// spec = {
//   width, height,
//   lanes?:  [{ id, label, x, w, color }]            swimlane columns
//   nodes:   [{ id, x, y, type, title, sub, color, w, h }]
//            type: 'process' | 'decision' | 'terminal' | 'handoff' | 'system'
//            (x, y) is the node centre
//   edges:   [{ from, to, fp, tp, label, dashed, via, lx, ly }]
//            fp/tp: port on each node - 't' | 'b' | 'l' | 'r'
//            via:   optional explicit bend points [[x, y], ...]
// }

const SIZE = {
  process: [196, 56],
  system: [196, 56],
  handoff: [196, 50],
  terminal: [180, 40],
  decision: [156, 76],
};

function box(node) {
  const [dw, dh] = SIZE[node.type] || SIZE.process;
  return { w: node.w || dw, h: node.h || dh };
}

function port(node, side) {
  const { w, h } = box(node);
  if (side === 't') return [node.x, node.y - h / 2];
  if (side === 'b') return [node.x, node.y + h / 2];
  if (side === 'l') return [node.x - w / 2, node.y];
  return [node.x + w / 2, node.y];
}

// Orthogonal route between two ports.
function route(a, fp, b, tp, via) {
  if (via && via.length) return [a, ...via, b];
  const horizontalStart = fp === 'l' || fp === 'r';
  const horizontalEnd = tp === 'l' || tp === 'r';
  if (a[0] === b[0] || a[1] === b[1]) return [a, b];
  if (horizontalStart && horizontalEnd) {
    const mx = (a[0] + b[0]) / 2;
    return [a, [mx, a[1]], [mx, b[1]], b];
  }
  if (!horizontalStart && !horizontalEnd) {
    const my = (a[1] + b[1]) / 2;
    return [a, [a[0], my], [b[0], my], b];
  }
  if (horizontalStart) return [a, [b[0], a[1]], b];
  return [a, [a[0], b[1]], b];
}

function labelPoint(points) {
  let best = 0;
  let bestLen = -1;
  for (let i = 0; i < points.length - 1; i++) {
    const len = Math.abs(points[i + 1][0] - points[i][0]) + Math.abs(points[i + 1][1] - points[i][1]);
    if (len > bestLen) { bestLen = len; best = i; }
  }
  const [p, q] = [points[best], points[best + 1]];
  return [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
}

function Lines({ text, x, y, size, color, weight, lineHeight }) {
  const lines = String(text || '').split('\n');
  const start = y - ((lines.length - 1) * lineHeight) / 2;
  return lines.map((line, i) => (
    <text key={i} x={x} y={start + i * lineHeight} textAnchor="middle" dominantBaseline="middle" fill={color} fontSize={size} fontWeight={weight}>
      {line}
    </text>
  ));
}

function Node({ node }) {
  const { w, h } = box(node);
  const accent = node.color || C.line2;
  const titleSize = 12.5;
  const hasSub = Boolean(node.sub);
  const titleLines = String(node.title).split('\n').length;
  const blockH = titleLines * 15 + (hasSub ? 14 : 0);
  const titleY = node.y - blockH / 2 + (titleLines * 15) / 2;
  const subY = node.y + blockH / 2 - 6;

  if (node.type === 'decision') {
    const pts = `${node.x},${node.y - h / 2} ${node.x + w / 2},${node.y} ${node.x},${node.y + h / 2} ${node.x - w / 2},${node.y}`;
    return (
      <g>
        <polygon points={pts} fill={C.panel2} stroke={accent} strokeWidth="1.5" />
        <Lines text={node.title} x={node.x} y={node.y} size={12} color={C.text} weight={600} lineHeight={14} />
      </g>
    );
  }
  if (node.type === 'terminal') {
    return (
      <g>
        <rect x={node.x - w / 2} y={node.y - h / 2} width={w} height={h} rx={h / 2} fill={C.deck} stroke={accent} strokeWidth="1.5" />
        <Lines text={node.title} x={node.x} y={node.y} size={12} color={C.text} weight={600} lineHeight={14} />
      </g>
    );
  }
  const handoff = node.type === 'handoff';
  const system = node.type === 'system';
  return (
    <g>
      <rect
        x={node.x - w / 2} y={node.y - h / 2} width={w} height={h} rx="2"
        fill={handoff ? 'transparent' : system ? C.deck : C.panel2}
        stroke={handoff ? accent : C.line2}
        strokeWidth={handoff ? 1.5 : 1}
        strokeDasharray={handoff ? '5 4' : undefined}
      />
      {!handoff && <rect x={node.x - w / 2} y={node.y - h / 2} width={3} height={h} fill={accent} />}
      <Lines text={node.title} x={node.x} y={titleY} size={titleSize} color={C.text} weight={600} lineHeight={15} />
      {hasSub && <text x={node.x} y={subY} textAnchor="middle" dominantBaseline="middle" fill={C.muted} fontSize="10.5">{node.sub}</text>}
    </g>
  );
}

export default function Flowchart({ spec, label, caption, minWidth = 0 }) {
  const markerId = 'arrow' + React.useId().replace(/:/g, '');
  const byId = Object.fromEntries(spec.nodes.map(n => [n.id, n]));
  const { width, height } = spec;
  return (
    <figure className="ops-flow">
      {minWidth ? <div className="ops-flow-hint">Scroll sideways to see the whole chart →</div> : null}
      <div className="ops-flow-scroll">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label} style={{ minWidth, maxWidth: width }} className="ops-flow-svg">
          <defs>
            <marker id={markerId} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill={C.text2} />
            </marker>
          </defs>

          {(spec.lanes || []).map((lane, i) => (
            <g key={lane.id}>
              <rect x={lane.x} y="0" width={lane.w} height={height} fill={i % 2 ? 'transparent' : C.deck} opacity={i % 2 ? 1 : 0.55} />
              {i > 0 && <line x1={lane.x} x2={lane.x} y1="0" y2={height} stroke={C.line} />}
              <rect x={lane.x} y="0" width={lane.w} height="3" fill={lane.color} />
              <text x={lane.x + lane.w / 2} y="26" textAnchor="middle" fill={C.text} fontSize="12" fontWeight="700" letterSpacing="0.08em" fontFamily="var(--font-mono)">{lane.label.toUpperCase()}</text>
              {lane.sub ? <text x={lane.x + lane.w / 2} y="44" textAnchor="middle" fill={C.muted} fontSize="10.5">{lane.sub}</text> : null}
            </g>
          ))}
          {spec.lanes ? <line x1="0" x2={width} y1="58" y2="58" stroke={C.line} /> : null}

          {spec.edges.map((edge, i) => {
            const a = byId[edge.from];
            const b = byId[edge.to];
            if (!a || !b) return null;
            const points = route(port(a, edge.fp || 'b'), edge.fp || 'b', port(b, edge.tp || 't'), edge.tp || 't', edge.via);
            const d = points.map((p, k) => `${k ? 'L' : 'M'}${p[0]} ${p[1]}`).join(' ');
            const [lx, ly] = edge.lx != null ? [edge.lx, edge.ly] : labelPoint(points);
            const tw = edge.label ? edge.label.length * 6 + 12 : 0;
            return (
              <g key={i}>
                <path d={d} fill="none" stroke={edge.dashed ? C.muted : C.text2} strokeWidth="1.5" strokeDasharray={edge.dashed ? '5 4' : undefined} markerEnd={`url(#${markerId})`} />
                {edge.label ? (
                  <g>
                    <rect x={lx - tw / 2} y={ly - 9} width={tw} height="18" rx="2" fill={C.void} stroke={C.line} />
                    <text x={lx} y={ly + 0.5} textAnchor="middle" dominantBaseline="middle" fill={edge.tone || C.text2} fontSize="10.5" fontFamily="var(--font-mono)">{edge.label}</text>
                  </g>
                ) : null}
              </g>
            );
          })}

          {spec.nodes.map(node => <Node key={node.id} node={node} />)}
        </svg>
      </div>
      {caption ? <figcaption className="ops-note">{caption}</figcaption> : null}
    </figure>
  );
}
