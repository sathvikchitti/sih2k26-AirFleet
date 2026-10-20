// Design tokens — "airframe" palette.
//
// Structure comes from Federal Standard 595 air-superiority camouflage greys
// (gunship / dark ghost / light ghost), status colours from the cockpit:
// HUD phosphor green, afterburner amber, master-caution red and
// air-superiority blue. Keep this in sync with the CSS variables in index.css.
// JS needs literal hex values because SVG presentation attributes and
// alpha-suffixed colours (e.g. `${C.crit}55`) cannot use CSS variables.
export const C = {
  void: '#0b0c0d',     // page background
  deck: '#08090a',     // sidebar, insets, chart wells
  panel: '#121416',    // cards
  panel2: '#181b1e',   // raised / hover
  line: '#25292e',     // hairline borders
  line2: '#363c43',    // strong borders, inputs
  paint: '#4e5359',    // FS 36118 gunship grey — neutral fills
  text: '#e5e7e2',     // placard white
  text2: '#b6bcc1',    // secondary text
  muted: '#878e95',    // labels, captions
  dim: '#5c636a',      // de-emphasised
  hud: '#8fe388',      // HUD phosphor — primary accent, "mission capable"
  ok: '#8fe388',
  warn: '#f2a33a',     // afterburner amber
  crit: '#f0524a',     // master caution red
  critDeep: '#a8403a', // darker red — second critical state in stacked status bars
  info: '#7aa6c8',     // air-superiority blue — maintenance / in-work
  tan: '#c8b07e',      // desert-camo tan — extra categorical series colour
};

// Categorical chart series, in fixed order (never cycled): HUD green,
// air-superiority blue, desert brass, night-vision violet. Mid-tone steps so
// they pass the dark-surface lightness band, chroma floor and colour-blind
// separation checks (validated against #121416 and #08090a). Status colours
// above stay reserved for state; these are for identity only.
export const CAT = ['#36a558', '#218cb5', '#bb881a', '#825eb9'];

export const FONT = {
  display: "'Big Shoulders', 'Barlow Condensed', 'Arial Narrow', sans-serif",
  sans: "'Instrument Sans', Inter, system-ui, 'Segoe UI', sans-serif",
  mono: "'Geist Mono', 'JetBrains Mono', Consolas, monospace",
};
