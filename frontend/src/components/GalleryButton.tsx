'use client';

import { useOverlay } from '@/lib/overlay-context';
import { NAV_LINK_CLASS } from './nav-chrome';

export default function GalleryButton({
  label,
  className = "",
}: {
  label: string;
  className?: string;
}) {
  const { toggle } = useOverlay();

  return (
    <button onClick={() => toggle('gallery')} className={`${NAV_LINK_CLASS} ${className}`}>
      {label}
    </button>
  );
}
