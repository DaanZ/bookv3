import { useState } from 'react';

import Patch from './Patch';

// The jacket, where one has been found, and the patch where none has.
//
// `api/enrich.py` looks every book up on Hardcover once, in the background, and stores
// the cover under data/covers — so `book.cover` is a path on this server, not a remote
// URL, and it is either there or it is not. Nothing here fetches, retries or offers to
// look anything up: a cover you have to ask for per book is not a cover.
//
// The patch stays either way. It is what says *what kind* of book this is before a word
// is read, which a jacket does not do at a glance, so on a cover it rides in the corner
// at the size of a spine label. Below 40px there is no room for it and the jacket is on
// its own — the rows that small carry the category in words anyway.

export default function Cover({ book, size = 56, ratio = 1.5 }) {
  const [broken, setBroken] = useState(false);
  const source = book?.cover;
  const height = Math.round(size * ratio);

  // A cover file that has gone missing under us lands here too, via onError. The patch
  // takes the jacket's shape rather than its own square, so a shelf where some books
  // were found on Hardcover and some were not still reads as one column of books.
  if (!source || broken) return <Patch patch={book?.patch} size={size} height={height} />;

  const tab = size >= 40 ? Math.round(size * 0.3) : 0;

  return (
    <div style={{ position: 'relative', flex: 'none', width: size, height }}>
      <img
        src={source}
        alt=""
        aria-hidden="true"
        onError={() => setBroken(true)}
        style={{
          display: 'block',
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          borderRadius: 'var(--radius-physical)',
          background: 'var(--bg-surface-hover)',
          border: '1px solid var(--border-subtle)',
          boxSizing: 'border-box',
        }}
      />
      {tab > 0 && (
        <div
          style={{
            position: 'absolute',
            left: 4,
            bottom: 4,
            borderRadius: 'var(--radius-physical)',
            overflow: 'hidden',
            // Lifted off the jacket rather than ringed in a surface colour, so it reads
            // the same on the shelf row, the library list and the finish card.
            boxShadow: '0 1px 5px rgba(0, 0, 0, 0.45)',
          }}
        >
          <Patch patch={book.patch} size={tab} />
        </div>
      )}
    </div>
  );
}
