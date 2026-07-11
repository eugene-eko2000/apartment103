'use client';

import { useState } from 'react';
import PhotoGallery from './PhotoGallery';

export default function GalleryButton() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="hover:text-teal-700 transition-colors cursor-pointer"
      >
        Gallery
      </button>
      {open && <PhotoGallery onClose={() => setOpen(false)} />}
    </>
  );
}
