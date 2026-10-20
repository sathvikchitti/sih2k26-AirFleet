import React from 'react';
import { PageHeader, SectionTitle } from '../components/ui.jsx';
import Flowchart from '../components/Flowchart.jsx';
import { C, CAT } from '../theme.js';

// Documentation — four chevron tabs hanging from a rail (Problem, Solution,
// How it works, Workflow). The Workflow tab has its own role switcher:
// Role 1 | Role 2 | Role 3 | Complete workflow.

const ROLE = {
  commander: { name: 'Fleet Commander', short: 'Commander', color: CAT[0] },
  base: { name: 'Base Manager', short: 'Base Manager', color: CAT[1] },
  logistics: { name: 'Logistics Officer', short: 'Logistics', color: CAT[2] },
  system: { name: 'Platform engines', short: 'System', color: C.paint },
};

const TABS = [
  ['problem', 'Problem'],
  ['solution', 'Solution'],
  ['how', 'How it\nworks'],
  ['workflow', 'Workflow'],
];

function ChevronTabs({ tab, setTab }) {
  const refs = React.useRef([]);
  const onKey = (event, index) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    event.preventDefault();
    const next = (index + (event.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length;
    setTab(TABS[next][0]);
    refs.current[next]?.focus();
  };
  return (
    <div className="ops-doc-rail">
      <div className="ops-doc-tabs" role="tablist" aria-label="Documentation sections">
        {TABS.map(([key, label], index) => (
          <button
            key={key}
            ref={el => { refs.current[index] = el; }}
            role="tab"
            id={`doc-tab-${key}`}
            aria-selected={tab === key}
            aria-controls={`doc-panel-${key}`}
            tabIndex={tab === key ? 0 : -1}
            className={`ops-doc-tab${tab === key ? ' is-active' : ''}`}
            onClick={() => setTab(key)}
            onKeyDown={event => onKey(event, index)}
          >
            <span>{label.split('\n').map((line, i) => <React.Fragment key={i}>{i ? <br /> : null}{line}</React.Fragment>)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Problem
// ---------------------------------------------------------------------------
const STATEMENT = [
  ['Problem statement ID', '26249'],
  ['Problem statement title', 'Air Power - Predictive Maintenance & Fleet Availability'],
  ['Organization', 'Ministry of Defence (MoD)'],
  ['Department', 'Defence Services Staff College'],
  ['Category', 'Software'],
  ['Theme', 'Transportation & Logistics'],
];

const PAIN = [
  ['Fragmented data', 'Health-monitoring systems, technical records, spares and maintenance agencies each keep their own data. Nobody sees one picture of an aircraft.'],
  ['Reactive maintenance', 'Work starts after a fault shows up, so the aircraft is already grounded when the job is planned.'],
  ['Late fault prediction', 'Without integrated condition data, degradation is noticed late instead of being forecast ahead of time.'],
  ['Avoidable downtime', 'The right part is often at a different base. Finding and moving it adds days the aircraft did not need to lose.'],
  ['Under-used critical assets', 'Spares sit idle at one base while another base has aircraft waiting for exactly those parts.'],
];

function CauseChain() {
  const steps = ['Data in separate systems', 'Faults found late', 'Maintenance planned after the fault', 'Part at the wrong base', 'Aircraft grounded longer', 'Low fleet availability'];
  return (
    <figure className="ops-flow">
      <ol className="ops-chain" aria-label="How fragmented data leads to low availability">
        {steps.map((s, i) => <li key={s} className={i === steps.length - 1 ? 'is-end' : undefined}>{s}</li>)}
      </ol>
      <figcaption className="ops-note">Each step feeds the next: disconnected data is why the fleet ends up with fewer flyable aircraft.</figcaption>
    </figure>
  );
}

function ProblemTab() {
  return (
    <>
      <SectionTitle>Problem statement details</SectionTitle>
      <div className="ops-card ops-table-scroll">
        <table className="ops-table ops-doc-kv" style={{ minWidth: 0 }}>
          <tbody>
            {STATEMENT.map(([k, v]) => (
              <tr key={k} className="ops-table-row"><th scope="row">{k}</th><td>{k === 'Problem statement ID' ? <span className="ops-id">{v}</span> : v}</td></tr>
            ))}
            <tr className="ops-table-row">
              <th scope="row">Description</th>
              <td>
                <ul className="ops-reasons" style={{ marginTop: 0 }}>
                  <li><b>Problem statement:</b> Low aircraft availability due to fragmented and largely reactive maintenance practices across the air fleet. Maintenance data from aircraft health-monitoring systems, technical records, spares and maintenance agencies is not adequately integrated, resulting in delayed fault prediction, avoidable aircraft downtime and sub-optimal utilisation of critical assets.</li>
                  <li><b>Technology opportunity:</b> AI/ML-based predictive maintenance, IoT/aircraft health monitoring, digital twins and an integrated maintenance analytics platform.</li>
                </ul>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <SectionTitle>Why availability is low</SectionTitle>
      <CauseChain />

      <SectionTitle>The five gaps we set out to close</SectionTitle>
      <div className="ops-doc-grid">
        {PAIN.map(([title, body]) => (
          <div key={title} className="ops-card ops-doc-card">
            <div className="ops-card-title">{title}</div>
            <p>{body}</p>
          </div>
        ))}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Solution
// ---------------------------------------------------------------------------
const ANSWERS = [
  ['Fragmented data', 'One platform links aircraft health predictions, maintenance events, work orders, inventory and transfers through a single API.'],
  ['Reactive maintenance', 'A validated prediction opens a predicted maintenance event before the aircraft fails, so work is planned ahead.'],
  ['Late fault prediction', 'A Random Forest model trained on NASA C-MAPSS FD001 engine data estimates remaining useful life (RUL) for each aircraft.'],
  ['Avoidable downtime', 'The recommendation engine ranks every feasible donor base by the fastest recovery time and shows the impact before anyone approves.'],
  ['Under-used critical assets', 'A cycle-based spares forecast and cross-base stock view show where parts are idle and where they will be needed.'],
];

const CAPABILITIES = [
  ['Predictive health', 'Remaining-useful-life estimates with an uncalibrated model-spread band. Official FD001 test: MAE 13.79 and RMSE 18.70 cycles over 100 test engines.'],
  ['Backend risk policy', 'Risk bands are computed by the server, not taken from the model: below 45 critical, below 60 high, below 80 medium by default.'],
  ['Maintenance cases', 'Predicted events, human triage into work orders, and a full timeline of predictions, decisions, transfers and audit entries per aircraft.'],
  ['Recommendation engine', 'Hard checks first (valid part, stock above reserve, minimum condition), then ranking by transfer ETA plus repair time, with reasons shown.'],
  ['Inventory & transfers', 'Reserves and condition are protected. Stock leaves the donor at dispatch and arrives once at receipt; maintenance reserves and then consumes the part.'],
  ['Readiness planning', 'A read-only what-if compares allocation policies, and a 300-scenario synthetic evaluation measured +5.05 pp availability from sharing spares.'],
  ['Role-based control', 'Commander, Base Manager and Logistics Officer each get only the actions their role allows, and every state change is audited.'],
];

function SolutionTab() {
  return (
    <>
      <div className="ops-card ops-callout" style={{ '--callout': C.hud, marginTop: 20 }}>
        <div className="ops-label" style={{ color: C.hud }}>What we built</div>
        <p className="ops-doc-lede">
          An integrated predictive-maintenance and fleet-availability platform. It turns machine-learning health predictions into
          maintenance work, finds the fastest way to get the right part to the right base, and keeps a human in charge of every decision.
        </p>
        <p className="ops-note" style={{ marginTop: 8 }}>The system recommends. People approve. Nothing moves until the responsible role acts.</p>
      </div>

      <SectionTitle>Each gap, and how the platform answers it</SectionTitle>
      <div className="ops-card ops-table-scroll">
        <table className="ops-table" style={{ minWidth: 560 }}>
          <thead><tr><th style={{ width: '28%' }}>Gap in the problem statement</th><th>What the platform does</th></tr></thead>
          <tbody>
            {ANSWERS.map(([gap, answer]) => (
              <tr key={gap} className="ops-table-row"><td><b>{gap}</b></td><td style={{ color: C.text2 }}>{answer}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      <SectionTitle>Core capabilities</SectionTitle>
      <div className="ops-doc-grid">
        {CAPABILITIES.map(([title, body]) => (
          <div key={title} className="ops-card ops-doc-card">
            <div className="ops-card-title">{title}</div>
            <p>{body}</p>
          </div>
        ))}
      </div>

      <SectionTitle>Technology</SectionTitle>
      <div className="ops-metric-strip">
        <div><div className="ops-label">Interface</div><div className="ops-doc-tech">React · Vite</div><div className="ops-metric-sub">Role-based dashboards</div></div>
        <div><div className="ops-label">API</div><div className="ops-doc-tech">FastAPI</div><div className="ops-metric-sub">Validation, permissions, audit</div></div>
        <div><div className="ops-label">Model</div><div className="ops-doc-tech">scikit-learn</div><div className="ops-metric-sub">Random Forest on NASA C-MAPSS FD001</div></div>
        <div><div className="ops-label">Data</div><div className="ops-doc-tech">In-memory</div><div className="ops-metric-sub">Repository layer ready for PostgreSQL</div></div>
      </div>
      <p className="ops-note" style={{ marginTop: 12 }}>
        Scope: a proof of concept on simulated engine data and synthetic fleet scenarios. It is not a certified maintenance or flight-release system.
      </p>
    </>
  );
}

// ---------------------------------------------------------------------------
// How it works
// ---------------------------------------------------------------------------
const ROLE_CARDS = [
  {
    key: 'commander',
    owns: 'The whole fleet',
    does: ['Watches fleet availability against the readiness target', 'Reviews at-risk aircraft across every base', 'Approves or rejects part-transfer recommendations', 'Runs read-only what-if and policy comparisons'],
    screens: 'Dashboard · Fleet · Bases · Aircraft · Maintenance · Resources · Recommendations',
    gives: 'Approved transfers to Logistics',
  },
  {
    key: 'base',
    owns: 'One base and its aircraft',
    does: ['Triages predicted events into work orders and picks the component', 'Requests parts the base does not hold', 'Starts maintenance once the part is on hand', 'Completes the work order so availability is recalculated'],
    screens: 'Dashboard · My Base · Aircraft · Maintenance · Resources',
    gives: 'Work orders to the recommendation engine, part requests to Logistics',
  },
  {
    key: 'logistics',
    owns: 'Physical stock and movements',
    does: ['Keeps inventory, reserves and part condition up to date', 'Approves, dispatches or cancels transfer requests', 'Confirms receipt so the part is usable at the destination', 'Uses the spares forecast to move stock before it is needed'],
    screens: 'Dashboard · Inventory · Components · Transfers · Maintenance Resources · Bases',
    gives: 'Received parts to the Base Manager',
  },
];

const LAYERS = [
  ['Interface', 'React dashboards for each role'],
  ['API', 'FastAPI: validation, role checks, audit log'],
  ['Engines', 'ML provider · risk policy · recommendation · transfers · forecast'],
  ['Data', 'Aircraft, predictions, work orders, inventory, transfers'],
];

const HANDOFFS = [
  ['System', 'A validated prediction scores each aircraft; high or critical risk opens a predicted maintenance event.'],
  ['Base Manager', 'Triages the event into a work order and chooses the component that needs replacing.'],
  ['System', 'Searches every base for that part, drops infeasible donors, and ranks the rest by recovery time and impact.'],
  ['Commander', 'Reviews the ranked options and approves one; the transfer is dispatched. (Or the Base Manager requests a part and Logistics approves it.)'],
  ['Logistics Officer', 'Tracks the transfer in transit and confirms receipt, which adds the part to the destination base’s stock.'],
  ['Base Manager', 'Starts maintenance, which reserves the part, then completes the work order, which consumes it.'],
  ['System', 'Recalculates the aircraft’s status and fleet availability, which the Commander sees on the dashboard.'],
];

function roleOf(name) {
  return name === 'System' ? ROLE.system : name === 'Commander' ? ROLE.commander : name === 'Base Manager' ? ROLE.base : ROLE.logistics;
}

function HowTab() {
  return (
    <>
      <SectionTitle>Architecture</SectionTitle>
      <div className="ops-layers" role="list">
        {LAYERS.map(([name, body], i) => (
          <div key={name} className="ops-layer" role="listitem">
            <span className="ops-label">{name}</span>
            <span>{body}</span>
            {i < LAYERS.length - 1 ? <span className="ops-layer-arrow" aria-hidden="true">↓</span> : null}
          </div>
        ))}
      </div>
      <p className="ops-note" style={{ marginTop: 10 }}>Requests flow down through the layers; every state-changing call is checked against the caller’s role before it runs.</p>

      <SectionTitle>The three roles</SectionTitle>
      <div className="ops-doc-roles">
        {ROLE_CARDS.map(card => {
          const role = ROLE[card.key];
          return (
            <div key={card.key} className="ops-card ops-doc-role" style={{ '--role': role.color }}>
              <div className="ops-label">Owns · {card.owns}</div>
              <div className="ops-card-title" style={{ marginTop: 8 }}>{role.name}</div>
              <ul className="ops-reasons">{card.does.map(item => <li key={item}>{item}</li>)}</ul>
              <div className="ops-doc-role-foot">
                <div><span className="ops-label">Screens</span><p>{card.screens}</p></div>
                <div><span className="ops-label">Hands off</span><p>{card.gives}</p></div>
              </div>
            </div>
          );
        })}
      </div>

      <SectionTitle>How they work together</SectionTitle>
      <ol className="ops-handoffs">
        {HANDOFFS.map(([who, what], i) => {
          const role = roleOf(who);
          return (
            <li key={i}>
              <span className="ops-handoff-who" style={{ '--role': role.color }}>{who}</span>
              <span>{what}</span>
            </li>
          );
        })}
      </ol>
      <p className="ops-note" style={{ marginTop: 10 }}>
        Each role can only take its own step: the backend rejects an approval from anyone but the Commander, a maintenance action from anyone but the Base Manager, and a transfer receipt from anyone but Logistics.
      </p>
    </>
  );
}

// ---------------------------------------------------------------------------
// Workflow flowcharts
// ---------------------------------------------------------------------------
const row = (r, base = 64, step = 96) => base + r * step;
const sys = ROLE.system.color, cmd = ROLE.commander.color, bm = ROLE.base.color, lg = ROLE.logistics.color;

const COMMANDER_FLOW = {
  width: 900, height: row(7) + 40,
  nodes: [
    { id: 'in', type: 'handoff', x: 450, y: row(0), title: 'From system', sub: 'ranked recommendation ready', color: sys },
    { id: 'review', type: 'process', x: 450, y: row(1), title: 'Review fleet readiness', sub: 'availability · risk · base gaps', color: cmd },
    { id: 'open', type: 'process', x: 450, y: row(2), title: 'Open recommendation', sub: 'donors · ETA · impact preview', color: cmd },
    { id: 'd', type: 'decision', x: 450, y: row(3), title: 'Approve\ntransfer?', color: cmd },
    { id: 'reject', type: 'process', x: 160, y: row(4), title: 'Reject', sub: 'recorded in the audit log', color: cmd },
    { id: 'approve', type: 'process', x: 450, y: row(4), title: 'Approve', sub: 'transfer dispatched', color: cmd },
    { id: 'toLog', type: 'handoff', x: 740, y: row(4), title: 'To Logistics', sub: 'track and receive the part', color: lg },
    { id: 'fromSys', type: 'handoff', x: 740, y: row(6), title: 'From system', sub: 'availability recalculated', color: sys },
    { id: 'monitor', type: 'process', x: 450, y: row(6), title: 'Monitor readiness', sub: 'gap to target closes', color: cmd },
    { id: 'plan', type: 'process', x: 450, y: row(7), title: 'Plan ahead', sub: 'what-if · policy evaluation', color: cmd },
  ],
  edges: [
    { from: 'in', to: 'review' },
    { from: 'review', to: 'open' },
    { from: 'open', to: 'd' },
    { from: 'd', to: 'approve', label: 'yes' },
    { from: 'd', to: 'reject', fp: 'l', tp: 't', label: 'no' },
    { from: 'reject', to: 'open', fp: 'b', tp: 'l', via: [[160, row(5)], [80, row(5)], [80, row(2)]], label: 're-evaluate later', dashed: true, lx: 80, ly: row(3) + 30 },
    { from: 'approve', to: 'toLog', fp: 'r', tp: 'l', label: 'handoff' },
    { from: 'approve', to: 'monitor', label: 'base repairs aircraft', dashed: true },
    { from: 'fromSys', to: 'monitor', fp: 'l', tp: 'r', label: 'dashboard' },
    { from: 'monitor', to: 'plan' },
  ],
};

const BASE_FLOW = {
  width: 900, height: row(7) + 40,
  nodes: [
    { id: 'in', type: 'handoff', x: 450, y: row(0), title: 'From system', sub: 'predicted maintenance event', color: sys },
    { id: 'd1', type: 'decision', x: 450, y: row(1), title: 'Needs\nwork?', color: bm },
    { id: 'dismiss', type: 'process', x: 160, y: row(1), title: 'Dismiss event', sub: 'recorded in the audit log', color: bm },
    { id: 'wo', type: 'process', x: 450, y: row(2), title: 'Create work order', sub: 'triage · choose component', color: bm },
    { id: 'd2', type: 'decision', x: 450, y: row(3), title: 'Part in\nlocal stock?', color: bm },
    { id: 'req', type: 'process', x: 740, y: row(3), title: 'Request the part', sub: 'or await Commander approval', color: bm },
    { id: 'log', type: 'handoff', x: 740, y: row(4), title: 'Logistics', sub: 'dispatches and receives part', color: lg },
    { id: 'start', type: 'process', x: 450, y: row(5), title: 'Start maintenance', sub: 'reserves the part', color: bm },
    { id: 'done', type: 'process', x: 450, y: row(6), title: 'Complete work order', sub: 'consumes the part', color: bm },
    { id: 'out', type: 'handoff', x: 450, y: row(7), title: 'To system', sub: 'aircraft & fleet availability', color: sys },
  ],
  edges: [
    { from: 'in', to: 'd1' },
    { from: 'd1', to: 'dismiss', fp: 'l', tp: 'r', label: 'no' },
    { from: 'd1', to: 'wo', label: 'yes' },
    { from: 'wo', to: 'd2' },
    { from: 'd2', to: 'req', fp: 'r', tp: 'l', label: 'no' },
    { from: 'req', to: 'log', label: 'request' },
    { from: 'log', to: 'start', fp: 'b', tp: 'r', label: 'part received' },
    { from: 'd2', to: 'start', label: 'yes' },
    { from: 'start', to: 'done' },
    { from: 'done', to: 'out' },
  ],
};

const LOGISTICS_FLOW = {
  width: 900, height: row(6) + 40,
  nodes: [
    { id: 'monitor', type: 'process', x: 450, y: row(0), title: 'Monitor inventory', sub: 'stock · reserves · forecast', color: lg },
    { id: 'baseReq', type: 'handoff', x: 160, y: row(1), title: 'Base Manager', sub: 'part request', color: bm },
    { id: 'review', type: 'process', x: 450, y: row(1), title: 'Review transfer request', sub: 'or create a forecast move', color: lg },
    { id: 'd', type: 'decision', x: 450, y: row(2), title: 'Stock above\nreserve & OK?', color: lg },
    { id: 'cancel', type: 'process', x: 160, y: row(3), title: 'Cancel request', sub: 'pending only', color: lg },
    { id: 'dispatch', type: 'process', x: 450, y: row(3), title: 'Approve & dispatch', sub: 'stock leaves the donor', color: lg },
    { id: 'cmd', type: 'handoff', x: 740, y: row(3), title: 'Commander', sub: 'approved recommendation', color: cmd },
    { id: 'transit', type: 'process', x: 450, y: row(4), title: 'In transit', sub: 'cannot be cancelled now', color: lg },
    { id: 'receive', type: 'process', x: 450, y: row(5), title: 'Confirm receipt', sub: 'destination stock +1', color: lg },
    { id: 'out', type: 'handoff', x: 450, y: row(6), title: 'To Base Manager', sub: 'part ready for maintenance', color: bm },
  ],
  edges: [
    { from: 'monitor', to: 'review' },
    { from: 'baseReq', to: 'review', fp: 'r', tp: 'l', label: 'request' },
    { from: 'review', to: 'd' },
    { from: 'd', to: 'cancel', fp: 'l', tp: 't', label: 'no' },
    { from: 'd', to: 'dispatch', label: 'yes' },
    { from: 'dispatch', to: 'transit' },
    { from: 'cmd', to: 'transit', fp: 'b', tp: 'r', label: 'already dispatched' },
    { from: 'transit', to: 'receive', label: 'arrives' },
    { from: 'receive', to: 'out' },
  ],
};

// Swimlanes: Commander | System | Base Manager | Logistics; time runs down.
const LANE_W = 260;
const lx = i => i * LANE_W + LANE_W / 2;
const r = n => 100 + n * 86;
const COMPLETE_FLOW = {
  width: LANE_W * 4, height: r(11) + 44,
  lanes: [
    { id: 'c', label: 'Commander', sub: 'approves', x: 0, w: LANE_W, color: cmd },
    { id: 's', label: 'System', sub: 'ML & decision engines', x: LANE_W, w: LANE_W, color: sys },
    { id: 'b', label: 'Base Manager', sub: 'triages & repairs', x: LANE_W * 2, w: LANE_W, color: bm },
    { id: 'l', label: 'Logistics', sub: 'moves stock', x: LANE_W * 3, w: LANE_W, color: lg },
  ],
  nodes: [
    { id: 's1', type: 'system', x: lx(1), y: r(0), title: 'Health prediction', sub: 'validated RUL · health score', color: sys },
    { id: 's2', type: 'decision', x: lx(1), y: r(1), title: 'High or\ncritical risk?', color: sys },
    { id: 's3', type: 'system', x: lx(1), y: r(2), title: 'Predicted maintenance\nevent', color: sys },
    { id: 'l0', type: 'process', x: lx(3), y: r(2), title: 'Inventory & forecast', sub: 'stock above reserve', color: lg },
    { id: 'b1', type: 'process', x: lx(2), y: r(3), title: 'Triage → work order', sub: 'chooses the component', color: bm },
    { id: 's4', type: 'system', x: lx(1), y: r(4), title: 'Rank feasible donors', sub: 'fastest recovery first', color: sys },
    { id: 'c1', type: 'decision', x: lx(0), y: r(5), title: 'Approve?', color: cmd },
    { id: 'b2', type: 'handoff', x: lx(2), y: r(5), title: 'Or request part', sub: 'direct to Logistics', color: bm },
    { id: 'c2', type: 'process', x: lx(0), y: r(6), title: 'Reject', sub: 'audited · aircraft waits', color: cmd },
    { id: 'l1', type: 'process', x: lx(3), y: r(6), title: 'Transfer in transit', sub: 'stock leaves donor', color: lg },
    { id: 'l2', type: 'process', x: lx(3), y: r(7), title: 'Receive part', sub: 'destination stock +1', color: lg },
    { id: 'b3', type: 'process', x: lx(2), y: r(8), title: 'Start maintenance', sub: 'reserves the part', color: bm },
    { id: 'b4', type: 'process', x: lx(2), y: r(9), title: 'Complete work order', sub: 'consumes the part', color: bm },
    { id: 's5', type: 'system', x: lx(1), y: r(10), title: 'Recalculate availability', sub: 'aircraft status · fleet %', color: sys },
    { id: 'c3', type: 'process', x: lx(0), y: r(11), title: 'Dashboard updated', sub: 'gap to readiness target', color: cmd },
  ],
  edges: [
    { from: 's1', to: 's2' },
    { from: 's2', to: 's3', label: 'yes' },
    { from: 's2', to: 's1', fp: 'r', tp: 'r', via: [[lx(1) + 112, r(1)], [lx(1) + 112, r(0)]], label: 'no · keep watching', lx: lx(1) + 112, ly: (r(0) + r(1)) / 2, dashed: true },
    { from: 's3', to: 'b1', fp: 'r', tp: 't', label: 'event' },
    { from: 'l0', to: 's4', fp: 'b', tp: 'r', label: 'stock levels', dashed: true, lx: lx(2) + 40, ly: r(4) },
    { from: 'b1', to: 's4', fp: 'b', tp: 't', label: 'work order' },
    { from: 's4', to: 'c1', fp: 'l', tp: 't', label: 'ranked options' },
    { from: 'c1', to: 'c2', label: 'no' },
    { from: 'c1', to: 'l1', fp: 'r', tp: 'l', label: 'yes · dispatch', lx: lx(2) - 20, ly: r(6) },
    { from: 'b1', to: 'b2', fp: 'r', tp: 'r', via: [[lx(2) + 116, r(3)], [lx(2) + 116, r(5)]], dashed: true, label: 'or', lx: lx(2) + 116, ly: r(4) - 26 },
    { from: 'b2', to: 'l1', fp: 'b', tp: 't', label: 'Logistics approves', dashed: true, lx: lx(3) - 10, ly: r(5) + 46 },
    { from: 'l1', to: 'l2', label: 'arrives' },
    { from: 'l2', to: 'b3', fp: 'l', tp: 't', label: 'part received' },
    { from: 'b3', to: 'b4' },
    { from: 'b4', to: 's5', fp: 'l', tp: 't', label: 'closed' },
    { from: 's5', to: 'c3', fp: 'l', tp: 't', label: 'fleet %' },
  ],
};

const STEPS = {
  commander: ['A ranked recommendation arrives from the system.', 'Review fleet readiness and the aircraft’s risk.', 'Open the recommendation: donors, ETA and impact preview.', 'Approve to dispatch the transfer, or reject (audited) and re-evaluate later.', 'Logistics tracks and receives the part; the base repairs the aircraft.', 'Watch availability recover on the dashboard, and plan with what-if and policy evaluation.'],
  base: ['A predicted maintenance event appears for an aircraft at the base.', 'Dismiss it (audited) if no work is needed, otherwise create a work order and choose the component.', 'If the part is not in local stock, request it or wait for the Commander to approve a recommendation.', 'Once the part is received, start maintenance — this reserves the part.', 'Complete the work order — this consumes the part and triggers recalculation of availability.'],
  logistics: ['Monitor inventory, reserves, condition and the spares forecast.', 'Review a Base Manager’s request, or create a move suggested by the forecast.', 'If stock is above reserve and in usable condition, approve and dispatch; otherwise cancel the pending request.', 'Commander-approved recommendations arrive already dispatched.', 'Confirm receipt so the destination stock rises and the base can start maintenance.'],
};

const WORKFLOWS = [
  ['commander', 'Role 1 · Commander'],
  ['base', 'Role 2 · Base Manager'],
  ['logistics', 'Role 3 · Logistics'],
  ['all', 'Complete workflow'],
];

function WorkflowTab() {
  const [which, setWhich] = React.useState('all');
  const spec = which === 'commander' ? COMMANDER_FLOW : which === 'base' ? BASE_FLOW : which === 'logistics' ? LOGISTICS_FLOW : COMPLETE_FLOW;
  const role = ROLE[which];
  return (
    <>
      <div className="ops-doc-subtabs" role="tablist" aria-label="Workflow view">
        {WORKFLOWS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={which === key} className={`ops-doc-subtab${which === key ? ' is-active' : ''}`} onClick={() => setWhich(key)}>
            {key !== 'all' ? <span className="ops-swatch" style={{ background: ROLE[key].color }} /> : null}
            {label}
          </button>
        ))}
      </div>

      <div className="ops-doc-flow-head">
        <div>
          <h3 className="ops-card-title">{which === 'all' ? 'Complete workflow across all roles' : `${role.name} workflow`}</h3>
          <p className="ops-note" style={{ marginTop: 6 }}>
            {which === 'all'
              ? 'Time runs top to bottom. Each column is one role; arrows show the hand-offs between them.'
              : 'Solid boxes are this role’s steps. Dashed boxes are hand-offs to or from another role.'}
          </p>
        </div>
        <div className="ops-legend">
          <span className="ops-legend-item"><span className="ops-swatch is-line" style={{ background: C.text2 }} />Main path</span>
          <span className="ops-legend-item"><span className="ops-swatch is-line ops-dash" />Alternative or feedback</span>
          {Object.values(ROLE).map(item => <span key={item.short} className="ops-legend-item"><span className="ops-swatch" style={{ background: item.color }} />{item.short}</span>)}
        </div>
      </div>

      <div className="ops-card" style={{ padding: 16 }}>
        <Flowchart
          spec={spec}
          minWidth={which === 'all' ? 860 : 720}
          label={which === 'all'
            ? 'Swimlane flowchart: a validated prediction raises a maintenance event, the Base Manager creates a work order, the system ranks donor bases, the Commander approves, Logistics moves and receives the part, the Base Manager repairs the aircraft, and the system recalculates fleet availability.'
            : `Flowchart of the ${role.name} workflow.`}
          caption={which === 'all'
            ? 'One full loop: from a health prediction to a repaired aircraft and an updated fleet availability. The loop repeats with the next prediction.'
            : null}
        />
      </div>

      {which !== 'all' && (
        <>
          <SectionTitle>Step by step</SectionTitle>
          <ol className="ops-handoffs">
            {STEPS[which].map((step, i) => <li key={i}><span className="ops-handoff-who" style={{ '--role': role.color }}>Step {i + 1}</span><span>{step}</span></li>)}
          </ol>
        </>
      )}
    </>
  );
}

export default function Documentation() {
  const [tab, setTab] = React.useState('problem');
  return (
    <div>
      <PageHeader title="Documentation" subtitle="The problem we were given, the solution we built, how the three roles work together, and the complete workflow." />
      <ChevronTabs tab={tab} setTab={setTab} />
      <div role="tabpanel" id={`doc-panel-${tab}`} aria-labelledby={`doc-tab-${tab}`} className="ops-doc-panel">
        {tab === 'problem' && <ProblemTab />}
        {tab === 'solution' && <SolutionTab />}
        {tab === 'how' && <HowTab />}
        {tab === 'workflow' && <WorkflowTab />}
      </div>
    </div>
  );
}
