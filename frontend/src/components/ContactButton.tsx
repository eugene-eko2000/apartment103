"use client";

import { useOverlay } from "@/lib/overlay-context";
import { NAV_ACTIVE_CLASS, NAV_LINK_CLASS } from "./nav-chrome";

export default function ContactButton({
  label,
  className = "",
}: {
  label: string;
  className?: string;
}) {
  const { active, toggle } = useOverlay();
  const isOpen = active === "contact";

  return (
    <button
      onClick={() => toggle("contact")}
      className={`${NAV_LINK_CLASS} ${isOpen ? NAV_ACTIVE_CLASS : ""} ${className}`}
    >
      {label}
    </button>
  );
}
