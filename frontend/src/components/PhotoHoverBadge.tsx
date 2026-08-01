"use client";

import { useState } from "react";
import { imageUrl, type ImageAsset } from "@/lib/api";

export default function PhotoHoverBadge({
  icon,
  label,
  images,
  maxPhotos = 2,
}: {
  icon: string;
  label: string;
  images: ImageAsset[];
  maxPhotos?: number;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const photos = images.slice(0, maxPhotos);

  return (
    <div
      className="relative"
      onMouseEnter={() => setIsOpen(true)}
      onMouseLeave={() => setIsOpen(false)}
    >
      <span className="flex items-center gap-1.5 bg-white/15 backdrop-blur-sm px-3 py-1.5 rounded-full text-sm text-white cursor-default">
        <span>{icon}</span>
        <span>{label}</span>
      </span>

      {isOpen && photos.length > 0 && (
        // `w-max`: without an explicit width, an absolutely-positioned box with only
        // `left` set is shrink-to-fit against its containing block (the badge span,
        // ~120px) — that squeezed both flex-shrinking <img>s down to fit inside the
        // badge's own width instead of sizing to the photos' natural width.
        <div className="absolute left-0 top-full pt-2 z-50 w-max">
          <div className="flex gap-2 bg-white/10 backdrop-blur-sm p-2.5 rounded-xl shadow-lg border border-white/20">
            {photos.map((photo) => (
              // eslint-disable-next-line @next/next/no-img-element -- backend-served, not a Next-optimizable local/static asset
              <img
                key={photo._id}
                src={imageUrl(photo.key)}
                alt={photo.alt || label}
                className="w-80 h-64 object-cover rounded-lg shrink-0"
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
