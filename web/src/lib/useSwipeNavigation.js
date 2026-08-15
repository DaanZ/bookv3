import { useCallback, useEffect, useRef, useState } from 'react';

// Turning the page by dragging it.
//
// Pointer events, not mouse or touch events: one code path covers a mouse, a trackpad
// and a finger, and pointer capture keeps the drag alive when the cursor leaves the
// card mid-throw.
//
// The gesture is a small state machine, because a page turn is three moments and only
// the first is under the reader's hand:
//
//   drag  — the page follows the pointer 1:1. No transition, or it would lag the hand.
//   out   — released past the threshold: the page leaves in the direction it was thrown.
//   in    — the new page arrives from the opposite edge.
//
// `out` and `in` are separated by the navigation itself. The commit fires at the end of
// `out`, so the parent swaps the content while nothing is on screen, and `in` starts
// from the far side on the very next frame.

// Past this, a release turns the page. Below it, the page falls back into place.
const DISTANCE_THRESHOLD = 72;

// A fast flick counts even if it never travelled far (px per ms).
const VELOCITY_THRESHOLD = 0.45;

// Movement under this is a tap — focus mode's click must survive a shaky hand.
const DRAG_SLOP = 6;

// How far the page has left when it is fully gone, and how far in the new one starts.
// The exit is longer than the entrance: the page is thrown out and set down.
const EXIT_TRAVEL = 340;
const ENTER_TRAVEL = 56;

// Both under --dur-max. Exit is roughly two-thirds of enter, as the token file requires.
const EXIT_MS = 170;
const ENTER_MS = 260;

// Pulling toward an edge with nothing behind it moves this fraction of the distance —
// the page gives a little, so the gesture is answered, and then refuses.
const EDGE_RESISTANCE = 0.32;

/**
 * @param onNext      turn forward — called at the end of the outgoing animation
 * @param onPrevious  turn back
 * @param canNext     false when there is no next page; the drag rubber-bands instead
 * @param canPrevious false when there is no previous page
 * @param reduced     honour prefers-reduced-motion: navigate, do not animate
 * @param enabled     false while something else owns the pointer
 */
export default function useSwipeNavigation({
  onNext,
  onPrevious,
  canNext = true,
  canPrevious = true,
  reduced,
  enabled = true,
}) {
  // phase drives the style; the ref lets pointer handlers read it without re-subscribing.
  const [phase, setPhase] = useState('idle');
  const [dx, setDx] = useState(0);
  const phaseRef = useRef('idle');
  const start = useRef(null);
  const dragged = useRef(false);
  const timers = useRef([]);

  const setPhaseBoth = useCallback((next) => {
    phaseRef.current = next;
    setPhase(next);
  }, []);

  const after = useCallback((ms, fn) => {
    const id = setTimeout(fn, ms);
    timers.current.push(id);
    return id;
  }, []);

  useEffect(
    () => () => {
      timers.current.forEach(clearTimeout);
      timers.current = [];
    },
    [],
  );

  const commit = useCallback(
    (direction) => {
      const go = direction < 0 ? onNext : onPrevious;

      if (reduced) {
        setDx(0);
        setPhaseBoth('idle');
        go();
        return;
      }

      setPhaseBoth('out');
      setDx(direction < 0 ? -EXIT_TRAVEL : EXIT_TRAVEL);

      after(EXIT_MS, () => {
        // Park the incoming page on the far side *before* the content changes, so the
        // new text is never painted at its resting position first.
        setDx(direction < 0 ? ENTER_TRAVEL : -ENTER_TRAVEL);
        setPhaseBoth('enter-armed');
        go();

        // Two frames: one for React to paint the new content at the offset, one to
        // start the transition from it. A single frame occasionally lands before paint
        // and the page simply appears, with no travel at all.
        requestAnimationFrame(() =>
          requestAnimationFrame(() => {
            setPhaseBoth('in');
            setDx(0);
            after(ENTER_MS, () => setPhaseBoth('idle'));
          }),
        );
      });
    },
    [onNext, onPrevious, reduced, after, setPhaseBoth],
  );

  const onPointerDown = useCallback(
    (event) => {
      // Only a primary button, and never while a turn is already in flight.
      if (!enabled || event.button !== 0 || phaseRef.current !== 'idle') return;
      // Let the controls keep their own clicks.
      if (event.target.closest('button, a, input, [data-no-swipe]')) return;

      start.current = { x: event.clientX, y: event.clientY, time: performance.now() };
      dragged.current = false;
    },
    [enabled],
  );

  const onPointerMove = useCallback(
    (event) => {
      if (!start.current) return;
      const moveX = event.clientX - start.current.x;
      const moveY = event.clientY - start.current.y;

      if (!dragged.current) {
        // Vertical intent belongs to the page, not to us.
        if (Math.abs(moveY) > Math.abs(moveX)) {
          start.current = null;
          return;
        }
        if (Math.abs(moveX) < DRAG_SLOP) return;
        dragged.current = true;
        setPhaseBoth('drag');
        event.currentTarget.setPointerCapture?.(event.pointerId);
      }

      const direction = moveX < 0 ? -1 : 1;
      const allowed = direction < 0 ? canNext : canPrevious;

      // The turn fires the moment the page is dragged far enough — it does not wait for
      // the button to come up. Past the threshold the decision is already made, and
      // holding the page there to ask "are you sure" is the hesitation this reader is
      // built to avoid. The pointer is released here so the drag cannot continue into
      // the outgoing animation.
      if (allowed && Math.abs(moveX) > DISTANCE_THRESHOLD) {
        event.currentTarget.releasePointerCapture?.(event.pointerId);
        start.current = null;
        commit(direction);
        return;
      }

      setDx(allowed ? moveX : moveX * EDGE_RESISTANCE);
    },
    [setPhaseBoth, canNext, canPrevious, commit],
  );

  const finish = useCallback(
    (event) => {
      if (!start.current) return;
      const moveX = event.clientX - start.current.x;
      const elapsed = Math.max(1, performance.now() - start.current.time);
      const velocity = Math.abs(moveX) / elapsed;
      const wasDragging = dragged.current;

      event.currentTarget.releasePointerCapture?.(event.pointerId);
      start.current = null;

      if (!wasDragging) return;

      // Anything that crossed the distance threshold has already turned, mid-drag. What
      // reaches here is a short gesture — so this is the flick: released close to where
      // it started, but fast enough to mean it. Dragged left, the page leaves left.
      const direction = moveX < 0 ? -1 : 1;
      const allowed = direction < 0 ? canNext : canPrevious;
      if (allowed && velocity > VELOCITY_THRESHOLD) {
        commit(direction);
        return;
      }

      // Not far enough: settle back to where it started.
      setPhaseBoth('settle');
      setDx(0);
      after(ENTER_MS, () => setPhaseBoth('idle'));
    },
    [commit, after, setPhaseBoth, canNext, canPrevious],
  );

  // A drag ends with a click event on the paragraph underneath. Focus mode would toggle
  // on every page turn without this.
  const swallowClick = useCallback((event) => {
    if (!dragged.current) return;
    event.preventDefault();
    event.stopPropagation();
    dragged.current = false;
  }, []);

  const moving = phase === 'out' || phase === 'in' || phase === 'settle';
  const duration = phase === 'out' ? EXIT_MS : ENTER_MS;
  const easing =
    phase === 'out' ? 'var(--ease-exit)' : phase === 'in' ? 'var(--ease-enter)' : 'var(--ease-move)';

  // Fades with distance travelled, so the page thins out as it goes rather than
  // blinking off at the end.
  const fade = Math.min(1, Math.abs(dx) / EXIT_TRAVEL);
  const opacity = phase === 'enter-armed' ? 0 : 1 - fade * 0.85;

  return {
    phase,
    dragging: phase === 'drag',
    /**
     * Turn the page the way a drag would, from a control.
     *
     * The button and the gesture were doing the same thing by two different routes —
     * one animated, one an instant swap — which made the buttons feel like a different
     * app. They share the animation now, and the direction matches the hand: forward
     * leaves to the left, back leaves to the right.
     */
    slideNext: () => (phaseRef.current === 'idle' && canNext ? commit(-1) : undefined),
    slideBack: () => (phaseRef.current === 'idle' && canPrevious ? commit(1) : undefined),
    handlers: {
      onPointerDown,
      onPointerMove,
      onPointerUp: finish,
      onPointerCancel: finish,
      onClickCapture: swallowClick,
    },
    style: {
      transform: `translate3d(${dx}px, 0, 0)`,
      opacity,
      transition: moving
        ? `transform ${duration}ms ${easing}, opacity ${duration}ms ${easing}`
        : 'none',
      // Vertical scrolling still belongs to the page; we only claim the horizontal axis.
      touchAction: 'pan-y',
      cursor: phase === 'drag' ? 'grabbing' : 'grab',
      // The page is a thing you move, not a document you mark up. Selection is off
      // everywhere on the surface so a drag across text turns the page like any other
      // drag, and never leaves a stray highlight behind.
      userSelect: 'none',
      willChange: phase === 'idle' ? 'auto' : 'transform, opacity',
    },
  };
}
