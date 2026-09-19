"use client";

import type { ReactNode } from "react";
import { useOverlay } from "@/lib/overlay-context";
import { NAV_ACTIVE_CLASS, NAV_LINK_CLASS } from "./nav-chrome";

export default function LocationButton({
  label,
  className = "",
  /** "nav" wears the header link styling; "plain" leaves all styling to
   *  `className`, for callers with their own look (e.g. the hero pill). */
  variant = "nav",
}: {
  label: ReactNode;
  className?: string;
  variant?: "nav" | "plain";
}) {
  const { active, toggle } = useOverlay();
  const isOpen = active === "location";

  return (
    <button
      onClick={() => toggle("location")}
      className={
        variant === "nav"
          ? `${NAV_LINK_CLASS} ${isOpen ? NAV_ACTIVE_CLASS : ""} ${className}`
          : className
      }
    >
      {label}
    </button>
  );
}
