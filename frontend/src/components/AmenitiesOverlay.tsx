'use client';

import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import SiteHeader from './SiteHeader';
import SiteFooter from './SiteFooter';
import type { Dictionary } from '@/app/[lang]/dictionaries';
import type { Locale } from '@/lib/i18n-config';

function CheckItem({ label }: { label: string }) {
  return (
    <li className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true" className="shrink-0 text-teal-600 dark:text-teal-400">
        <path d="M3 8.5l3 3 7-7" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span>{label}</span>
    </li>
  );
}

export default function AmenitiesOverlay({
  lang,
  dict,
  onClose,
}: {
  lang: Locale;
  dict: Dictionary;
  onClose: () => void;
}) {
  const a = dict.amenities;

  const BADGES = [
    a.badges.entireApartment,
    a.badges.size,
    a.badges.privateKitchen,
    a.badges.privateBathroom,
    a.badges.balcony,
    a.badges.lakeView,
    a.badges.gardenView,
    a.badges.mountainView,
    a.badges.bath,
    a.badges.dishwasher,
    a.badges.flatScreenTv,
    a.badges.coffeeMachine,
    a.badges.freeWifi,
  ];

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.overflow = 'hidden';
    document.body.style.paddingRight = `${scrollbarWidth}px`;
    return () => {
      document.body.style.overflow = '';
      document.body.style.paddingRight = '';
    };
  }, []);

  return createPortal(
    <div className="fixed inset-0 z-50 flex flex-col bg-gray-50/75 dark:bg-gray-950/80 backdrop-blur-md">
      {/* Reuses the homepage's own header — the "amenities" nav slot swaps
          to a close control here (onCloseAmenities) instead of relinquishing
          the layer to a nested overlay. */}
      <SiteHeader lang={lang} dict={dict} onCloseAmenities={onClose} />

      {/* `relative` makes this the containing block for the close button
          below, so it sits on the content view (not overlapping the header)
          and stays put while the inner div scrolls underneath it. */}
      <div className="relative flex-1 min-h-0">
        <button
          onClick={onClose}
          aria-label={a.backHome}
          className="absolute top-5 right-6 sm:top-8 sm:right-12 z-10 text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-200 transition-colors text-3xl sm:text-5xl leading-none cursor-pointer"
        >
          ✕
        </button>

        <div className="h-full overflow-y-auto">
        <div className="max-w-5xl mx-auto px-6 py-10">
          <h1 className="text-3xl lg:text-4xl font-bold text-gray-900 dark:text-gray-100 mb-2">{a.pageTitle}</h1>
          <p className="text-gray-500 dark:text-gray-400 mb-6">{a.subtitle}</p>

          {/* Badges */}
          <div className="flex flex-wrap gap-2 mb-8">
            {BADGES.map((label) => (
              <span
                key={label}
                className="bg-teal-50 dark:bg-teal-900/30 text-teal-700 dark:text-teal-300 text-sm font-medium px-3 py-1.5 rounded-full"
              >
                {label}
              </span>
            ))}
          </div>

          {/* Overview */}
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-5 sm:p-6 mb-6">
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
              {a.sizeLabel} <span className="text-gray-900 dark:text-gray-100 font-medium">{a.badges.size}</span>
            </p>
            <dl className="space-y-1.5 text-sm max-w-sm">
              <div className="flex justify-between gap-4">
                <dt className="font-medium text-gray-900 dark:text-gray-100">{a.rooms.bedroom1}</dt>
                <dd className="text-gray-500 dark:text-gray-400">{a.singleBeds} 🛏</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="font-medium text-gray-900 dark:text-gray-100">{a.rooms.bedroom2}</dt>
                <dd className="text-gray-500 dark:text-gray-400">{a.singleBeds} 🛏</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="font-medium text-gray-900 dark:text-gray-100">{a.rooms.livingRoom}</dt>
                <dd className="text-gray-500 dark:text-gray-400">{a.sofaBed} 🛋</dd>
              </div>
            </dl>
            <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed mt-5 pt-5 border-t border-gray-100 dark:border-gray-700">
              {a.description}
            </p>
          </div>

          {/* Kitchen / Bathroom / View */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-5">
              <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm mb-3">{a.kitchen.title}</h2>
              <ul className="space-y-2">
                {a.kitchen.items.map((item) => <CheckItem key={item} label={item} />)}
              </ul>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-5">
              <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm mb-3">{a.bathroom.title}</h2>
              <ul className="space-y-2">
                {a.bathroom.items.map((item) => <CheckItem key={item} label={item} />)}
              </ul>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-5">
              <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm mb-3">{a.view.title}</h2>
              <ul className="space-y-2">
                {a.view.items.map((item) => <CheckItem key={item} label={item} />)}
              </ul>
            </div>
          </div>

          {/* Facilities */}
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-5 sm:p-6 mb-6">
            <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm mb-4">{a.facilities.title}</h2>
            <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-2">
              {a.facilities.items.map((item) => <CheckItem key={item} label={item} />)}
            </ul>
          </div>

          {/* Smoking */}
          <p className="text-sm text-gray-500 dark:text-gray-400">
            <span className="font-medium text-gray-900 dark:text-gray-100">{a.smoking.title}:</span> {a.smoking.value}
          </p>
        </div>
        </div>
      </div>

      <SiteFooter dict={dict} />
    </div>,
    document.body
  );
}
