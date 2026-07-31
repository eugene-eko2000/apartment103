"use client";

import { useEffect, useState } from "react";

// Matches the fixed header's h-16 in page.tsx — subtracted so the spacer
// lines up with the actual visible viewport below the nav bar.
const HEADER_HEIGHT_PX = 64;

// Mobile-only (desktop keeps the widget in its normal grid position): reserves
// a window-height-sized gap above the booking widget so the hero's background
// photo is the first thing visible. The widget itself stays fully rendered —
// its position below the fold is what keeps it out of view until scrolled to.
export default function MobileBookingReveal({ children }: { children: React.ReactNode }) {
  const [spacerHeight, setSpacerHeight] = useState(0);

  useEffect(() => {
    const updateHeight = () => setSpacerHeight(Math.max(0, window.innerHeight - HEADER_HEIGHT_PX));
    updateHeight();
    window.addEventListener("resize", updateHeight);
    return () => window.removeEventListener("resize", updateHeight);
  }, []);

  return (
    <>
      <div aria-hidden="true" className="lg:hidden" style={{ height: spacerHeight }} />
      {children}
    </>
  );
}
