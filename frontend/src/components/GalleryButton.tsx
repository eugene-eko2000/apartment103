'use client';

import { useState } from 'react';
import PhotoGallery, { type GalleryDict } from './PhotoGallery';

export default function GalleryButton({ label, dict }: { label: string; dict: GalleryDict }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="text-left hover:text-teal-700 dark:hover:text-teal-400 transition-colors cursor-pointer"
      >
        {label}
      </button>
      {open && <PhotoGallery onClose={() => setOpen(false)} dict={dict} />}
    </>
  );
}
