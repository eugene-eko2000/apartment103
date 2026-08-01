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

export default function PhotoGallery({ onClose, dict }: Props) {
  const [photos, setPhotos] = useState<ImageAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(0);
  // The photo animating out during a transition — kept mounted alongside
  // the new "selected" photo just long enough for both to slide together.
  const [outgoing, setOutgoing] = useState<ImageAsset | null>(null);
  const stripRef = useRef<HTMLDivElement>(null);
  const imageAreaRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const mainImgRef = useRef<HTMLImageElement>(null);
  const outgoingImgRef = useRef<HTMLImageElement>(null);
  const thumbRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const touch = useRef({ startX: 0, startY: 0 });
  const lastSelected = useRef(selected);
  // Bumped on every transition so a late `onfinish` from a superseded
  // animation (rapid clicking) can't clear a newer transition's outgoing photo.
  const transitionSeq = useRef(0);
  const pendingTransition = useRef<{ direction: number; distance: number; seq: number } | null>(null);
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

  // Swipe left/right on the main image to move between photos (mobile)
  useEffect(() => {
    const el = imageAreaRef.current;
    if (!el) return;

    const SWIPE_THRESHOLD = 40;

    const start = (e: TouchEvent) => {
      const t = e.touches[0];
      touch.current = { startX: t.pageX, startY: t.pageY };
    };

    const end = (e: TouchEvent) => {
      const t = e.changedTouches[0];
      const dx = t.pageX - touch.current.startX;
      const dy = t.pageY - touch.current.startY;
      if (Math.abs(dx) < SWIPE_THRESHOLD || Math.abs(dx) < Math.abs(dy)) return;
      if (dx > 0) prev();
      else next();
    };

    el.addEventListener('touchstart', start, { passive: true });
    el.addEventListener('touchend', end, { passive: true });
    return () => {
      el.removeEventListener('touchstart', start);
      el.removeEventListener('touchend', end);
    };
  }, [prev, next]);

  // Kick off a transition whenever the selection changes — covers arrow
  // clicks, keyboard, thumbnail clicks, and swipe alike, since they all
  // just move `selected`. Stashes the outgoing photo so both it and the
  // new one can slide together; the actual `.animate()` calls happen in
  // the layout effect below, once the outgoing <img> has actually mounted.
  useEffect(() => {
    const from = lastSelected.current;
    lastSelected.current = selected;
    if (selected === from) return;
    const prevPhoto = photos[from];
    if (!prevPhoto) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const direction = selected > from ? 1 : -1;
    const distance = viewportRef.current?.clientWidth || 120;
    pendingTransition.current = { direction, distance, seq: ++transitionSeq.current };
    setOutgoing(prevPhoto);
  }, [selected, photos]);

  // Runs synchronously right after `outgoing` mounts (pre-paint), so both
  // images start animating together with no dropped frame in between.
  useLayoutEffect(() => {
    const pending = pendingTransition.current;
    if (!outgoing || !pending) return;
    pendingTransition.current = null;
    const { direction, distance, seq } = pending;
    const timing: KeyframeAnimationOptions = { duration: 500, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' };

    outgoingImgRef.current?.animate(
      [{ transform: 'translateX(0)' }, { transform: `translateX(${-direction * distance}px)` }],
      timing,
    );
    const anim = mainImgRef.current?.animate(
      [{ transform: `translateX(${direction * distance}px)` }, { transform: 'translateX(0)' }],
      timing,
    );
    if (anim) {
      anim.onfinish = () => {
        // Only clear if no newer transition has started since.
        if (transitionSeq.current === seq) setOutgoing(null);
      };
    }
  }, [outgoing]);

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

  useEffect(() => {
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.overflow = 'hidden';
    document.body.style.paddingRight = `${scrollbarWidth}px`;
    return () => {
      document.body.style.overflow = '';
      document.body.style.paddingRight = '';
    };
  }, []);

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
          {outgoing && (
            // The inset lives on this wrapper, not the <img> itself — a
            // replaced element's max-width resolves against the full
            // containing block regardless of its own inset, so the inset
            // has to shrink a plain box for max-w-full to clamp against.
            <div className="absolute inset-y-0 inset-x-2.5 sm:inset-x-0 flex items-center justify-center">
              {/* eslint-disable-next-line @next/next/no-img-element -- backend-served, not a Next-optimizable local/static asset */}
              <img
                ref={outgoingImgRef}
                key={`outgoing-${outgoing.key}`}
                src={imageUrl(outgoing.key)}
                alt=""
                aria-hidden="true"
                width={outgoing.width ?? undefined}
                height={outgoing.height ?? undefined}
                className="max-h-full max-w-full w-auto h-auto rounded-2xl"
              />
            </div>
          )}
          {photos[selected] && (
            <div className="absolute inset-y-0 inset-x-2.5 sm:inset-x-0 flex items-center justify-center">
              {/* eslint-disable-next-line @next/next/no-img-element -- backend-served, not a Next-optimizable local/static asset */}
              <img
                ref={mainImgRef}
                key={photos[selected].key}
                src={imageUrl(photos[selected].key)}
                alt={`${dict.apartmentPhoto} ${selected + 1}`}
                width={photos[selected].width ?? undefined}
                height={photos[selected].height ?? undefined}
                className="max-h-full max-w-full w-auto h-auto rounded-2xl"
              />
            </div>
          )}
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
