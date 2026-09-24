import { useState } from 'react';

import Patch from '../../components/Patch';

/**
 * The cover, where the library has one, falling back to the patch.
 *
 * Only on this screen. The reader's surfaces use coloured patches on purpose — a patch
 * says what family a book belongs to at a glance and never fails to load — and swapping
 * them for covers everywhere would be redesigning the shelf, not filling it in. The
 * library is the overview, and an overview is where a cover earns its place.
 *
 * The ground is painted in the cover's own dominant colour so the row does not flash an
 * empty box while the image arrives from Hardcover's CDN.
 */
export default function Cover({ book, size = 26 }) {
  const [failed, setFailed] = useState(false);
  if (!book.cover || failed) return <Patch patch={book.patch} size={size} />;

  return (
    <img
      src={book.cover}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
      style={{
        width: size,
        height: Math.round(size * 1.5),
        objectFit: 'cover',
        borderRadius: 3,
        background: book.coverColor || 'var(--bg-surface-hover)',
        flexShrink: 0,
      }}
    />
  );
}
