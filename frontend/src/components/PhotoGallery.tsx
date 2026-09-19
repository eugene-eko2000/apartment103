'use client';

import { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { imageUrl, listImagesByLabel, type ImageAsset } from '@/lib/api';

export interface GalleryDict {
  closeGallery: string;
  previousPhoto: string;
  nextPhoto: string;
  photo: string;
  apartmentPhoto: string;
}

interface Props {
  onClose: () => void;
  dict: GalleryDict;
}

// Gutter between neighbouring slides, so photos never touch while dragging.
const SLIDE_GAP = 16;
// Gesture tuning (all in CSS px / px per ms).
const AXIS_LOCK = 8; // movement before the gesture commits to an axis
const COMMIT_DISTANCE = 60; // drag past this and the photo changes
const COMMIT_FRACTION = 0.25; // …or past this share of the viewport, whichever is smaller
const COMMIT_VELOCITY = 0.45; // a fast flick commits on much less distance
const FLICK_MIN_DISTANCE = 12;
const EDGE_RESISTANCE = 0.28; // rubber band when there is no neighbour to reveal
const SLIDE_DURATION = 500; // full-width slide; shorter distances scale down
const SLIDE_EASING = 'cubic-bezier(0.22, 1, 0.36, 1)';

export default function PhotoGallery({ onClose, dict }: Props) {
  const [photos, setPhotos] = useState<ImageAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(0);
  const stripRef = useRef<HTMLDivElement>(null);
  const imageAreaRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  // Holds the previous/current/next slides; everything animates by moving it.
  const trackRef = useRef<HTMLDivElement>(null);
  const trackAnim = useRef<Animation | null>(null);
  const thumbRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const lastSelected = useRef(selected);
  // Where the track should start its slide-in from when a swipe (rather than
  // a click) caused the selection change — lets the photo carry on from
  // exactly where the finger left it instead of jumping a full width.
  const pendingStartX = useRef<number | null>(null);
  // Read during pointer handling, which is bound once and must not go stale.
  const stateRef = useRef({ selected: 0, count: 0 });
  const swipe = useRef({
    id: -1,
    active: false,
    axis: null as null | 'x' | 'y',
    startX: 0,
    startY: 0,
    baseX: 0,
    dx: 0,
    lastX: 0,
    lastT: 0,
    velocity: 0,
  });
  // pending = mousedown happened; active = grab mode engaged; wasGrabbed = carry into click handler
  const drag = useRef({
    pending: false,
    active: false,
    wasGrabbed: false,
    startX: 0,
    scrollLeft: 0,
    timer: null as ReturnType<typeof setTimeout> | null,
  });

  // Admin-managed via the "gallery" label (Photos panel) rather than a
  // static file list — adding/removing/reordering photos there updates the
  // gallery with no frontend rebuild.
  useEffect(() => {
    listImagesByLabel('gallery')
      .then(setPhotos)
      .catch(() => setPhotos([]))
      .finally(() => setLoading(false));
  }, []);

  const prev = useCallback(() => setSelected(i => Math.max(0, i - 1)), []);
  const next = useCallback(() => setSelected(i => Math.min(photos.length - 1, i + 1)), [photos.length]);

  // One slide step: the viewport plus the gutter between slides.
  const slideWidth = useCallback(() => (viewportRef.current?.clientWidth || 120) + SLIDE_GAP, []);

  // Keep the pointer handlers' view of the selection current without
  // rebinding them (and losing an in-flight gesture) on every change.
  useLayoutEffect(() => {
    stateRef.current = { selected, count: photos.length };
  });

  const setTrackX = useCallback((x: number) => {
    if (trackRef.current) trackRef.current.style.transform = `translateX(${x}px)`;
  }, []);

  // The track's live position, so a gesture can pick a slide up mid-flight.
  const trackX = useCallback(() => {
    const track = trackRef.current;
    if (!track) return 0;
    const value = getComputedStyle(track).transform;
    if (!value || value === 'none') return 0;
    try {
      return new DOMMatrixReadOnly(value).m41;
    } catch {
      return 0;
    }
  }, []);

  // Move the track to `to`, animating in from `from` unless motion is reduced.
  // Duration scales with the distance actually left to travel, so finishing a
  // half-completed swipe feels like a nudge rather than a fresh slide.
  const settle = useCallback((from: number, to: number) => {
    const track = trackRef.current;
    if (!track) return;
    trackAnim.current?.cancel();
    trackAnim.current = null;
    setTrackX(to);
    if (from === to) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const ratio = Math.min(1, Math.abs(from - to) / slideWidth());
    const anim = track.animate(
      [{ transform: `translateX(${from}px)` }, { transform: `translateX(${to}px)` }],
      { duration: Math.max(180, ratio * SLIDE_DURATION), easing: SLIDE_EASING },
    );
    trackAnim.current = anim;
    anim.onfinish = () => {
      if (trackAnim.current === anim) trackAnim.current = null;
    };
  }, [setTrackX, slideWidth]);

  // Drag-to-scroll on thumbnail strip
  useEffect(() => {
    const el = stripRef.current;
    if (!el) return;

    const enterGrab = () => {
      drag.current.active = true;
      el.style.cursor = 'grabbing';
      document.body.style.userSelect = 'none';
    };

    const down = (e: MouseEvent) => {
      drag.current.pending = true;
      drag.current.active = false;
      drag.current.startX = e.pageX;
      drag.current.scrollLeft = el.scrollLeft;
      // Enter grab mode after a short hold even without movement
      drag.current.timer = setTimeout(enterGrab, 150);
    };

    const move = (e: MouseEvent) => {
      if (!drag.current.pending) return;
      const dx = e.pageX - drag.current.startX;
      // Immediate grab on movement beyond threshold
      if (!drag.current.active && Math.abs(dx) > 4) {
        clearTimeout(drag.current.timer!);
        enterGrab();
      }
      if (drag.current.active) {
        el.scrollLeft = drag.current.scrollLeft - dx;
      }
    };

    const up = () => {
      clearTimeout(drag.current.timer!);
      drag.current.wasGrabbed = drag.current.active;
      drag.current.pending = false;
      drag.current.active = false;
      el.style.cursor = '';
      document.body.style.userSelect = '';
    };

    // Prevent native browser drag on images inside the strip
    const preventDrag = (e: Event) => e.preventDefault();

    el.addEventListener('mousedown', down);
    el.addEventListener('dragstart', preventDrag);
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
    return () => {
      clearTimeout(drag.current.timer!);
      el.removeEventListener('mousedown', down);
      el.removeEventListener('dragstart', preventDrag);
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
    };
  }, []);

  // Swipe/drag the main image: the track follows the pointer from the first
  // few pixels of the gesture, and only the *finish* is animated — either
  // carrying the photo the rest of the way or springing it back.
  useEffect(() => {
    const el = imageAreaRef.current;
    if (!el) return;

    const down = (e: PointerEvent) => {
      // Arrows live inside this area; let them behave as plain buttons.
      if ((e.target as HTMLElement | null)?.closest('button')) return;
      if (!e.isPrimary || swipe.current.active) return;
      // Take over from a slide already in flight at its current position.
      const baseX = trackX();
      trackAnim.current?.cancel();
      trackAnim.current = null;
      setTrackX(baseX);
      swipe.current = {
        id: e.pointerId,
        active: true,
        axis: null,
        startX: e.clientX,
        startY: e.clientY,
        baseX,
        dx: 0,
        lastX: e.clientX,
        lastT: e.timeStamp,
        velocity: 0,
      };
      el.setPointerCapture(e.pointerId);
    };

    const move = (e: PointerEvent) => {
      const s = swipe.current;
      if (!s.active || e.pointerId !== s.id) return;
      const dx = e.clientX - s.startX;
      const dy = e.clientY - s.startY;

      if (s.axis === null) {
        if (Math.abs(dx) < AXIS_LOCK && Math.abs(dy) < AXIS_LOCK) return;
        s.axis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y';
      }
      if (s.axis !== 'x') return;

      const dt = e.timeStamp - s.lastT;
      if (dt > 0) s.velocity = (e.clientX - s.lastX) / dt;
      s.lastX = e.clientX;
      s.lastT = e.timeStamp;

      // Rubber-band at the ends, where there is no neighbour to pull in.
      const { selected: at, count } = stateRef.current;
      const noNeighbour = (dx > 0 && at === 0) || (dx < 0 && at >= count - 1);
      s.dx = noNeighbour ? dx * EDGE_RESISTANCE : dx;
      setTrackX(s.baseX + s.dx);
    };

    const finish = (e: PointerEvent, cancelled: boolean) => {
      const s = swipe.current;
      if (!s.active || e.pointerId !== s.id) return;
      s.active = false;
      if (el.hasPointerCapture(s.id)) el.releasePointerCapture(s.id);
      if (s.axis !== 'x') return;

      const from = s.baseX + s.dx;
      const width = slideWidth();
      const flick = !cancelled && Math.abs(s.velocity) > COMMIT_VELOCITY && Math.abs(s.dx) > FLICK_MIN_DISTANCE;
      const dragged = !cancelled && Math.abs(s.dx) > Math.min(COMMIT_DISTANCE, width * COMMIT_FRACTION);
      const direction = flick ? (s.velocity < 0 ? 1 : -1) : s.dx < 0 ? 1 : -1;
      const target = stateRef.current.selected + direction;

      if ((flick || dragged) && target >= 0 && target < stateRef.current.count) {
        // The target slide is currently `direction * width` away inside the
        // track; once it becomes the selected one the track resets to 0, so
        // start the animation from the offset that keeps it where it is now.
        pendingStartX.current = from + direction * width;
        setSelected(target);
      } else {
        settle(from, 0);
      }
    };

    const up = (e: PointerEvent) => finish(e, false);
    const cancel = (e: PointerEvent) => finish(e, true);

    el.addEventListener('pointerdown', down);
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', cancel);
    return () => {
      el.removeEventListener('pointerdown', down);
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', cancel);
    };
  }, [setTrackX, settle, slideWidth, trackX]);

  // Slide the track whenever the selection changes — arrow clicks, keyboard,
  // thumbnails and swipes all just move `selected`. Runs pre-paint so the
  // freshly laid out track never shows at its resting position first.
  useLayoutEffect(() => {
    const from = lastSelected.current;
    lastSelected.current = selected;
    const startX = pendingStartX.current;
    pendingStartX.current = null;
    if (selected === from) return;
    settle(startX ?? (selected > from ? 1 : -1) * slideWidth(), 0);
  }, [selected, settle, slideWidth]);

  // Scroll active thumbnail into view whenever selection changes
  useEffect(() => {
    thumbRefs.current[selected]?.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest',
      inline: 'center',
    });
  }, [selected]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft') prev();
      if (e.key === 'ArrowRight') next();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, prev, next]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex flex-col"
      style={{ background: 'rgba(10,10,10,0.72)', backdropFilter: 'blur(3px)' }}
      onClick={onClose}
    >
      {/* Close button */}
      <button
        onClick={onClose}
        aria-label={dict.closeGallery}
        className="absolute top-3 right-2.5 sm:top-6 sm:right-8 z-10 text-white/70 hover:text-white transition-colors text-3xl sm:text-5xl leading-none"
      >
        ✕
      </button>

      {/* ── Main image ── */}
      <div
        ref={imageAreaRef}
        className="relative flex-1 flex items-center justify-center min-h-0 sm:px-20 pt-12 pb-2 sm:pt-16 sm:pb-4"
        onClick={e => e.stopPropagation()}
        // Keep horizontal gestures for the gallery; leave vertical ones to the
        // browser (which then fires pointercancel and we spring back).
        style={{ touchAction: 'pan-y' }}
      >
        <button
          onClick={prev}
          disabled={selected === 0}
          aria-label={dict.previousPhoto}
          className="absolute left-2.5 sm:left-6 z-10 text-white text-3xl sm:text-5xl px-1 py-2 sm:px-2 sm:py-3 rounded-full bg-black/20 hover:bg-black/50 disabled:opacity-0 transition-all"
        >
          ‹
        </button>

        <div ref={viewportRef} className="relative flex items-center justify-center h-full w-full overflow-hidden">
          {!loading && photos.length === 0 && (
            <p className="text-white/70 text-sm">No photos yet.</p>
          )}
          <div ref={trackRef} className="absolute inset-0" style={{ willChange: 'transform' }}>
            {[-1, 0, 1].map(offset => {
              const photo = photos[selected + offset];
              if (!photo) return null;
              const current = offset === 0;
              return (
                // Keyed by photo, so the slide that scrolls into the centre
                // keeps its already-decoded <img> instead of remounting.
                // The horizontal inset is padding on this box rather than an
                // inset on the <img>: a replaced element's max-width resolves
                // against the full containing block regardless of its own
                // inset, so max-w-full needs a shrunken box to clamp against.
                <div
                  key={photo._id}
                  className="absolute inset-0 flex items-center justify-center px-2.5 sm:px-0"
                  style={{ transform: `translateX(calc(${offset * 100}% + ${offset * SLIDE_GAP}px))` }}
                  aria-hidden={!current}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element -- backend-served, not a Next-optimizable local/static asset */}
                  <img
                    src={imageUrl(photo.key)}
                    alt={current ? `${dict.apartmentPhoto} ${selected + 1}` : ''}
                    width={photo.width ?? undefined}
                    height={photo.height ?? undefined}
                    draggable={false}
                    className="max-h-full max-w-full w-auto h-auto rounded-2xl select-none"
                  />
                </div>
              );
            })}
          </div>
        </div>

        <button
          onClick={next}
          disabled={selected >= photos.length - 1}
          aria-label={dict.nextPhoto}
          className="absolute right-2.5 sm:right-6 z-10 text-white text-3xl sm:text-5xl px-1 py-2 sm:px-2 sm:py-3 rounded-full bg-black/20 hover:bg-black/50 disabled:opacity-0 transition-all"
        >
          ›
        </button>
      </div>

      {/* ── Thumbnail strip ── */}
      <div
        className="shrink-0 py-2 sm:py-4 sm:px-8"
        onClick={e => e.stopPropagation()}
      >
        <div
          ref={stripRef}
          className="flex gap-1.5 overflow-x-auto"
          // "safe center" centers the strip when it fits, but falls back to
          // start-aligned once it overflows — plain `center` would center
          // the overflow on both sides and leave the first thumbnails
          // unreachable by scrolling (scrollLeft can't go negative).
          style={{ scrollbarWidth: 'none', cursor: 'grab', padding: '4px', justifyContent: 'safe center' }}
          onClickCapture={e => {
            if (drag.current.wasGrabbed) { e.stopPropagation(); drag.current.wasGrabbed = false; }
          }}
        >
          {photos.map((photo, i) => (
            <button
              key={photo._id}
              ref={el => { thumbRefs.current[i] = el; }}
              onClick={() => setSelected(i)}
              aria-label={`${dict.photo} ${i + 1}`}
              className={[
                'relative shrink-0 rounded-md overflow-hidden transition-all duration-150',
                i === selected
                  ? 'ring-2 ring-teal-400 opacity-100 scale-105'
                  : 'opacity-50 hover:opacity-80',
              ].join(' ')}
              style={{ width: 44, height: 59, cursor: 'inherit' }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- backend-served, not a Next-optimizable local/static asset */}
              <img
                src={imageUrl(photo.key)}
                alt=""
                className="absolute inset-0 w-full h-full object-cover"
              />
            </button>
          ))}
        </div>
      </div>
    </div>,
    document.body
  );
}
