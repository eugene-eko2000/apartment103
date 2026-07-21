"use client";

import { useEffect, useRef, useState } from "react";
import { clearGuestSession, onGuestSessionChange, readGuestSession } from "@/lib/guest-auth";
import LoginModal, { type LoginModalDict } from "@/components/LoginModal";
import MyBookingsModal, { type MyBookingsDict } from "@/components/MyBookingsModal";

export interface UserMenuDict {
  login: string;
  accountMenu: string;
  myBookings: string;
  logout: string;
  loginModal: LoginModalDict;
  myBookingsModal: MyBookingsDict;
}

export default function UserMenu({ dict }: { dict: UserMenuDict }) {
  const [ready, setReady] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [loginOpen, setLoginOpen] = useState(false);
  const [myBookingsOpen, setMyBookingsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const sync = () => setLoggedIn(readGuestSession() !== null);
    // Deferred to a microtask so the localStorage read (and resulting
    // setState) isn't synchronous within the effect body, avoiding a
    // same-tick cascading render.
    queueMicrotask(() => {
      sync();
      setReady(true);
    });
    return onGuestSessionChange(sync);
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  // Reserve the icon's footprint before the first client render decides
  // whether a session exists, so the header doesn't visibly shift.
  if (!ready) return <div className="w-8 h-8" />;

  if (!loggedIn) {
    return (
      <>
        <button
          type="button"
          onClick={() => setLoginOpen(true)}
          className="hover:text-teal-700 dark:hover:text-teal-400 transition-colors cursor-pointer"
        >
          {dict.login}
        </button>
        {loginOpen && (
          <LoginModal
            dict={dict.loginModal}
            onClose={() => setLoginOpen(false)}
            onLoggedIn={() => setLoginOpen(false)}
          />
        )}
      </>
    );
  }

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={() => setMenuOpen((v) => !v)}
        aria-label={dict.accountMenu}
        aria-expanded={menuOpen}
        className="w-8 h-8 rounded-full flex items-center justify-center text-white cursor-pointer"
        style={{ background: "linear-gradient(135deg, #0f766e, #0891b2)" }}
      >
        <UserIcon />
      </button>

      {menuOpen && (
        <div className="absolute right-0 top-full pt-2 z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-100 dark:border-gray-700 py-1 min-w-[160px]">
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                setMyBookingsOpen(true);
              }}
              className="w-full text-left px-4 py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer"
            >
              {dict.myBookings}
            </button>
            <button
              type="button"
              onClick={() => {
                clearGuestSession();
                setMenuOpen(false);
              }}
              className="w-full text-left px-4 py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer"
            >
              {dict.logout}
            </button>
          </div>
        </div>
      )}

      {myBookingsOpen && (
        <MyBookingsModal dict={dict.myBookingsModal} onClose={() => setMyBookingsOpen(false)} />
      )}
    </div>
  );
}

function UserIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="5.25" r="2.75" stroke="currentColor" strokeWidth="1.5" />
      <path d="M2.5 14c0-2.5 2.46-4.25 5.5-4.25S13.5 11.5 13.5 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
