import { useEffect, useState } from 'react';

import Patch from '../components/Patch';
import Spinner from '../components/Spinner';
import { Indexing, Summarising } from '../components/Waiting';
import { Button, Card, Chip, ProgressBar, QuietLink } from '../components/ui';
import { PALETTE_NAMES, paletteFor } from '../lib/reading';

// The bench. Every component the reader is built from, on one page, in both registers
// and all five palettes — so a design question can be answered by looking at the thing
// itself instead of by finding a screen that happens to be showing it.
//
// Three rules it follows, and they are what make it worth having:
//
// * **It renders the real components.** Not copies, not screenshots. If `Spinner` is
//   wrong here it is wrong in the app, and a fix here is the fix everywhere. A gallery
//   of look-alikes would drift from the app within a week and quietly lie after that.
// * **It talks to nothing.** No profile, no shelf, no key. It is reachable on a plane,
//   with the API stopped, and it still shows every state — including the ones that are
//   hard to reach in the app because they need an upload or a finish to happen.
// * **It is not on any route the reader can wander into.** It mounts on `#design` only,
//   so the app itself is unchanged and there is no "design" button to explain.
//
// Open it at /#design.

const PATCHES = [
  { name: 'bands · self-help', shape: 'bands', c1: '#67482F', c2: '#E59312', c3: '#F4B315' },
  { name: 'rings · spirituality', shape: 'rings', c1: '#0C617C', c2: '#03B1AB', c3: '#FFD167' },
  { name: 'checks · technology', shape: 'checks', c1: '#073A4B', c2: '#03B1AB', c3: '#0C617C' },
];

const MONO = "400 11.5px 'IBM Plex Mono', monospace";

function Section({ title, note, children }) {
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <h2
          style={{
            margin: 0,
            font: "500 15px 'Space Grotesk', system-ui",
            color: 'var(--text-primary)',
          }}
        >
          {title}
        </h2>
        {note && <span style={{ font: MONO, color: 'var(--text-muted)' }}>{note}</span>}
      </div>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'flex-end',
          gap: 20,
          padding: 20,
          borderRadius: 14,
          border: '1px solid var(--border-subtle)',
          background: 'var(--bg-surface)',
        }}
      >
        {children}
      </div>
    </section>
  );
}

// A specimen and its name, so feedback can point at something by the name the code uses.
function Item({ label, children, align = 'center' }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: align, gap: 8 }}>
      {children}
      <span style={{ font: MONO, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{label}</span>
    </div>
  );
}

export default function Design() {
  const [day, setDay] = useState(false);
  const [palette, setPalette] = useState('sunset');
  // The spinner is the thing most often being judged, and judging motion means watching
  // it start. Remounting is the only honest way to see the first second again.
  const [spinKey, setSpinKey] = useState(1);
  const [done, setDone] = useState(4);

  useEffect(() => {
    document.body.style.background = day ? '#E6DED0' : '#04181B';
  }, [day]);

  const stops = paletteFor(palette, day, 8);

  return (
    <div
      className={day ? 'shore' : ''}
      style={{
        minHeight: '100vh',
        padding: '32px clamp(16px, 5vw, 56px) 80px',
        background: 'var(--bg-shell)',
        color: 'var(--text-primary)',
      }}
    >
      <header
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: 14,
          paddingBottom: 22,
          marginBottom: 26,
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <h1 style={{ margin: 0, font: "500 18px 'Space Grotesk', system-ui" }}>The bench</h1>
        <span style={{ font: MONO, color: 'var(--text-muted)' }}>
          every component, both registers, five palettes
        </span>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* The register is a different room, so it loads rather than animating —
              the same rule the app follows. */}
          <Button size="sm" variant="secondary" onClick={() => setDay((d) => !d)}>
            {day ? 'Day · cane paper' : 'Night · deep water'}
          </Button>
          {PALETTE_NAMES.map((name) => (
            <button
              key={name}
              type="button"
              className="tap"
              onClick={() => setPalette(name)}
              style={{
                width: 'auto',
                padding: '6px 11px',
                borderRadius: 9,
                font: "500 11.5px 'Space Grotesk', system-ui",
                background: palette === name ? 'var(--accent)' : 'transparent',
                color: palette === name ? 'var(--accent-on)' : 'var(--text-secondary)',
                border: `1px solid ${palette === name ? 'var(--accent)' : 'var(--border-strong)'}`,
              }}
            >
              {name}
            </button>
          ))}
        </div>
      </header>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 34, maxWidth: 1100 }}>
        <Section
          title="Spinner · the mark put to work"
          note="eight plates and a core; the core looks somewhere new every 2.6s and the plates lag. Nothing rotates."
        >
          <Item label="76px · default">
            <Spinner key={`a${spinKey}`} size={76} delay={0} palette={palette} />
          </Item>
          <Item label="46px · the floor">
            <Spinner key={`b${spinKey}`} size={46} delay={0} palette={palette} />
          </Item>
          <Item label="44px · refuses to draw">
            <Spinner key={`c${spinKey}`} size={44} delay={0} palette={palette} />
          </Item>
          <Item label="with a label">
            <Spinner key={`d${spinKey}`} size={56} delay={0} palette={palette} label="Working" />
          </Item>
          <Item label="seam · gold, a join only">
            <Spinner key={`e${spinKey}`} variant="seam" size={68} delay={0} />
          </Item>
          <Item label="restart the motion">
            <Button size="sm" variant="secondary" onClick={() => setSpinKey((k) => k + 1)}>
              Play again
            </Button>
          </Item>
        </Section>

        <Section
          title="Waiting · the two composite states"
          note="hard to reach in the app: one needs an upload running, the other an index pass"
        >
          <div style={{ flex: '1 1 460px', minWidth: 300 }}>
            <Summarising done={done} total={9} palette={palette} day={day} />
          </div>
          <Item label={`done = ${done} of 9`}>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button size="sm" variant="secondary" onClick={() => setDone((d) => Math.max(0, d - 1))}>
                –
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setDone((d) => Math.min(9, d + 1))}>
                +
              </Button>
            </div>
          </Item>
          <div style={{ flex: '1 1 320px' }}>
            <Indexing total={271} />
          </div>
        </Section>

        <Section title="Button" note="three variants, three sizes, and the disabled state of each">
          {['primary', 'secondary', 'quiet'].map((variant) => (
            <Item key={variant} label={variant}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {['sm', 'md', 'lg'].map((size) => (
                  <Button key={size} variant={variant} size={size}>
                    {size}
                  </Button>
                ))}
                <Button variant={variant} disabled>
                  disabled
                </Button>
              </div>
            </Item>
          ))}
          <Item label="QuietLink">
            <QuietLink onClick={() => {}}>Back to shelf</QuietLink>
          </Item>
        </Section>

        <Section title="Chip" note="tones carry meaning; seam is gold and means a join, nothing else">
          {['current', 'claimed', 'seam', 'expired', 'neutral'].map((tone) => (
            <Item key={tone} label={tone}>
              <Chip tone={tone}>{tone}</Chip>
            </Item>
          ))}
        </Section>

        <Section title="Card" note="four elevations — surfaces step, they never lift, scale or glow">
          {['plinth', 'table', 'seat', 'shelf'].map((elevation) => (
            <Item key={elevation} label={elevation}>
              <Card elevation={elevation} style={{ width: 150, height: 84, padding: 14 }}>
                <span style={{ font: MONO, color: 'var(--text-secondary)' }}>{elevation}</span>
              </Card>
            </Item>
          ))}
        </Section>

        <Section
          title="ProgressBar"
          note="the gradient runs the reading palette; an unstarted book must show nothing"
        >
          {[0, 12, 50, 100].map((pct) => (
            <Item key={pct} label={`${pct}% · gradient`} align="stretch">
              <div style={{ width: 210 }}>
                <ProgressBar pct={pct} gradient={stops} />
              </div>
            </Item>
          ))}
          <Item label="flat accent" align="stretch">
            <div style={{ width: 210 }}>
              <ProgressBar pct={62} />
            </div>
          </Item>
        </Section>

        <Section title="Patch" note="drawn in CSS from api/patches.py — three shapes, two sizes">
          {PATCHES.map((patch) => (
            <Item key={patch.name} label={patch.name}>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 10 }}>
                <Patch patch={patch} size={56} />
                <Patch patch={patch} size={34} />
              </div>
            </Item>
          ))}
        </Section>

        <Section
          title="Highlight bands"
          note={`${palette} sampled to 8 stops in this register — the colours a page is marked in`}
        >
          {stops.map((colour, i) => (
            <Item key={colour + i} label={colour}>
              <span
                style={{
                  display: 'inline-block',
                  padding: '4px 10px',
                  borderRadius: 6,
                  font: "500 14px 'Lexend', system-ui",
                  color: colour,
                }}
              >
                highlighted
              </span>
            </Item>
          ))}
        </Section>

        <Section title="Type" note="the three families, at the sizes the reader actually uses">
          <Item label="Lexend · reading body 19/1.75" align="flex-start">
            <span style={{ font: "400 19px/1.75 'Lexend', system-ui", maxWidth: 460, display: 'block' }}>
              The first forty per cent of a book carries eighty per cent of the bar.
            </span>
          </Item>
          <Item label="Space Grotesk · UI 15" align="flex-start">
            <span style={{ font: "500 15px 'Space Grotesk', system-ui" }}>Finish book</span>
          </Item>
          <Item label="IBM Plex Mono · data 11.5" align="flex-start">
            <span style={{ font: MONO, color: 'var(--text-muted)' }}>271 books · 201 read</span>
          </Item>
        </Section>
      </div>
    </div>
  );
}
