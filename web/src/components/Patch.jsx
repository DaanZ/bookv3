// The category patch: a 4px-radius square, drawn in CSS, that says what kind of book
// this is before a word is read. 56px on the shelf, 34px in the reader header and on
// the recommendation. Shape and colours come from the API (api/patches.py).

export default function Patch({ patch, size = 56, height = size }) {
  const spec = patch || { shape: 'bands', c1: '#67482F', c2: '#E59312', c3: '#F4B315' };
  const frame = {
    flex: 'none',
    width: size,
    // Square everywhere the design draws it; jacket-shaped only where it stands in for
    // a cover, so the shelf keeps one column of book-shaped things either way.
    height,
    borderRadius: 'var(--radius-physical)',
    overflow: 'hidden',
    background: spec.c1,
  };

  if (spec.shape === 'checks') {
    return (
      <div style={frame} aria-hidden="true">
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gridTemplateRows: '1fr 1fr',
            height: '100%',
          }}
        >
          <div style={{ background: spec.c1 }} />
          <div style={{ background: spec.c2 }} />
          <div style={{ background: spec.c3 }} />
          <div style={{ background: spec.c1 }} />
        </div>
      </div>
    );
  }

  if (spec.shape === 'rings') {
    // The demo scales the rings with the patch: 38/16 at 56px, 24/10 at 34px.
    const outer = Math.round(size * (38 / 56));
    const core = Math.round(size * (16 / 56));
    return (
      <div style={frame} aria-hidden="true">
        <div
          style={{
            height: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: spec.c1,
          }}
        >
          <div
            style={{
              width: outer,
              height: outer,
              borderRadius: '50%',
              background: spec.c2,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <div style={{ width: core, height: core, borderRadius: '50%', background: spec.c3 }} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={frame} aria-hidden="true">
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ flex: 3, background: spec.c1 }} />
        <div style={{ flex: 2, background: spec.c2 }} />
        <div style={{ flex: 1, background: spec.c3 }} />
      </div>
    </div>
  );
}
