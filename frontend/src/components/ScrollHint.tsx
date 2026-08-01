"use client";

import { useEffect, useState } from "react";

// id of the app's real scrollable container (frontend/src/app/[lang]/page.tsx)
const PAGE_SCROLL_ID = "page-scroll";
// id of the page's footer — always visible, pinned to the bottom of the
// h-screen shell alongside #page-scroll, never scrolled away. Its live
// height is measured so this hint can sit just above it instead of
// overlapping its (opaque) background.
const FOOTER_ID = "site-footer";
// id of the booking widget's anchor wrapper (frontend/src/components/MobileBookingReveal.tsx)
const BOOKING_WIDGET_ID = "booking-widget";

// Mobile-only "Book" nudge, fixed just above the footer. Visible while the
// page is at the very top (i.e. before the user has started scrolling
// toward the booking widget), fades out as soon as scrolling starts, and
// fades back in if scrolled back up to the top. Clicking it scrolls the
// booking widget into view.
export default function ScrollHint({ label }: { label: string }) {
  const [atTop, setAtTop] = useState(true);
  const [footerHeight, setFooterHeight] = useState(0);

  useEffect(() => {
    const scroller = document.getElementById(PAGE_SCROLL_ID);
    if (!scroller) return;
    const handleScroll = () => setAtTop(scroller.scrollTop <= 0);
    scroller.addEventListener("scroll", handleScroll, { passive: true });
    return () => scroller.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    const footer = document.getElementById(FOOTER_ID);
    if (!footer) return;
    const update = () => setFooterHeight(footer.getBoundingClientRect().height);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(footer);
    return () => observer.disconnect();
  }, []);

  const scrollToWidget = () => {
    document.getElementById(BOOKING_WIDGET_ID)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <button
      type="button"
      onClick={scrollToWidget}
      className={`lg:hidden fixed inset-x-0 z-40 flex items-center justify-center gap-4 bg-transparent border-none transition-opacity duration-500 ease-out ${
        atTop ? "opacity-100 pointer-events-auto cursor-pointer" : "opacity-0 pointer-events-none"
      }`}
      style={{ bottom: footerHeight + 16 }}
    >
      <DownArrow />
      <span className="text-white text-lg font-semibold [text-shadow:0_1px_3px_rgba(0,0,0,0.45)]">
        {label}
      </span>
      <DownArrow />
    </button>
  );
}

function DownArrow() {
  return (
    <svg
      className="w-7 h-7 text-white animate-bounce [filter:drop-shadow(0_1px_2px_rgba(0,0,0,0.45))]"
      viewBox="0 0 24 24"
      fill="none"
    >
      <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
