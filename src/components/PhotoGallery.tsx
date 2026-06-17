'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import Image from 'next/image';

const PHOTOS = [
  '20260614_133654.jpeg',
  '20260614_133717.jpeg',
  '20260614_133835.jpeg',
  '20260614_133840.jpeg',
  '20260614_134008.jpeg',
  '20260614_134017.jpeg',
  '20260614_134117.jpeg',
  '20260614_134200.jpeg',
  '20260614_134244.jpeg',
  '20260614_134259.jpeg',
  '20260614_134352.jpeg',
  '20260614_134400.jpeg',
  '20260614_134410.jpeg',
  '20260614_134531.jpeg',
  '20260614_134601.jpeg',
  '20260614_134606.jpeg',
  '20260614_134612.jpeg',
  '20260614_134724.jpeg',
  '20260614_134737.jpeg',
  '20260614_135021.jpeg',
  '20260614_135040.jpeg',
  '20260614_135044.jpeg',
  '20260614_135144.jpeg',
  '20260614_135149.jpeg',
  '20260614_135214.jpeg',
  '20260614_135221.jpeg',
  '20260614_135347.jpeg',
  '20260614_135402.jpeg',
  '20260614_135550.jpeg',
  '20260614_135610.jpeg',
  '20260614_135628.jpeg',
  '20260614_135633.jpeg',
  '20260614_140151.jpeg',
  '20260614_140213.jpeg',
  '20260614_140222.jpeg',
  '20260614_140225.jpeg',
  '20260614_140559.jpeg',
  '20260614_141026.jpeg',
  '20260614_141031.jpeg',
  '20260614_141320.jpeg',
  '20260614_141327.jpeg',
  '20260614_141349.jpeg',
  '20260614_141637.jpeg',
  '20260614_142319.jpeg',
  '20260614_143829.jpeg',
  '20260614_143914.jpeg',
  '20260614_144852.jpeg',
  '20260614_144940.jpeg',
  '20260614_144955.jpeg',
  '20260614_145202.jpeg',
  '20260614_145237.jpeg',
  '20260614_145238.jpeg',
  '20260614_145239(0).jpeg',
  '20260614_145239.jpeg',
];

interface Props {
  onClose: () => void;
}

export default function PhotoGallery({ onClose }: Props) {
  const [selected, setSelected] = useState(0);
  const stripRef = useRef<HTMLDivElement>(null);
  const thumbRefs = useRef<(HTMLButtonElement | null)[]>([]);
  // pending = mousedown happened; active = grab mode engaged; wasGrabbed = carry into click handler
  const drag = useRef({
    pending: false,
    active: false,
    wasGrabbed: false,
    startX: 0,
    scrollLeft: 0,
    timer: null as ReturnType<typeof setTimeout> | null,
  });

  const prev = useCallback(() => setSelected(i => Math.max(0, i - 1)), []);
  const next = useCallback(() => setSelected(i => Math.min(PHOTOS.length - 1, i + 1)), []);

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
        aria-label="Close gallery"
        className="absolute top-6 right-8 z-10 text-white/70 hover:text-white transition-colors text-5xl leading-none"
      >
        ✕
      </button>

      {/* ── Main image ── */}
      <div
        className="relative flex-1 flex items-center justify-center min-h-0 px-20 pt-16 pb-4"
        onClick={e => e.stopPropagation()}
      >
        <button
          onClick={prev}
          disabled={selected === 0}
          aria-label="Previous photo"
          className="absolute left-6 z-10 text-white text-5xl px-2 py-3 rounded-full bg-black/20 hover:bg-black/50 disabled:opacity-0 transition-all"
        >
          ‹
        </button>

        <div className="flex items-center justify-center h-full w-full">
          <Image
            key={PHOTOS[selected]}
            src={`/gallery/${PHOTOS[selected]}`}
            alt={`Apartment photo ${selected + 1}`}
            width={900}
            height={1000}
            className="max-h-full max-w-full w-auto h-auto rounded-2xl"
            priority
          />
        </div>

        <button
          onClick={next}
          disabled={selected === PHOTOS.length - 1}
          aria-label="Next photo"
          className="absolute right-6 z-10 text-white text-5xl px-2 py-3 rounded-full bg-black/20 hover:bg-black/50 disabled:opacity-0 transition-all"
        >
          ›
        </button>
      </div>

      {/* ── Thumbnail strip ── */}
      <div
        className="shrink-0 py-4 px-8"
        onClick={e => e.stopPropagation()}
      >
        <div
          ref={stripRef}
          className="flex gap-1.5 overflow-x-auto"
          style={{ scrollbarWidth: 'none', cursor: 'grab', padding: '4px' }}
          onClickCapture={e => {
            if (drag.current.wasGrabbed) { e.stopPropagation(); drag.current.wasGrabbed = false; }
          }}
        >
          {PHOTOS.map((photo, i) => (
            <button
              key={photo}
              ref={el => { thumbRefs.current[i] = el; }}
              onClick={() => setSelected(i)}
              aria-label={`Photo ${i + 1}`}
              className={[
                'relative shrink-0 rounded-md overflow-hidden transition-all duration-150',
                i === selected
                  ? 'ring-2 ring-teal-400 opacity-100 scale-105'
                  : 'opacity-50 hover:opacity-80',
              ].join(' ')}
              style={{ width: 44, height: 59, cursor: 'inherit' }}
            >
              <Image
                src={`/gallery/thumbs/${photo}`}
                alt=""
                fill
                className="object-cover"
                sizes="44px"
              />
            </button>
          ))}
        </div>
      </div>
    </div>,
    document.body
  );
}
