'use client';

import { useOverlay } from '@/lib/overlay-context';
import { NAV_ACTIVE_CLASS, NAV_LINK_CLASS } from './nav-chrome';

export default function AmenitiesButton({
  label,
  className = "",
}: {
  label: string;
  className?: string;
}) {
  const { active, toggle } = useOverlay();
  const isOpen = active === 'amenities';

  return (
    <button
      onClick={() => toggle('amenities')}
      className={`${NAV_LINK_CLASS} ${isOpen ? NAV_ACTIVE_CLASS : ''} ${className}`}
    >
      {label}
    </button>
  );
}
