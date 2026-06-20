import Image from "next/image";
import BookingWidget from "@/components/BookingWidget";
import GalleryButton from "@/components/GalleryButton";

const FEATURES = [
  { icon: "🛏", label: "2 Bedrooms" },
  { icon: "🚿", label: "2 Bathrooms" },
  { icon: "👥", label: "Up to 5 guests" },
  { icon: "🏔", label: "Lake & Mountain view" },
  { icon: "📶", label: "Free Wi-Fi" },
  { icon: "🅿️", label: "Free parking" },
  { icon: "🍳", label: "Full kitchen" },
];

export default function Home() {
  return (
    <div>
      {/* ── FIXED BACKGROUND ────────────────────────────── */}
      <div className="fixed inset-0 -z-10">
        <Image
          src="/hero2.jpeg"
          alt="Apartment view with Lake Walensee and mountains"
          fill
          priority
          className="object-cover object-center"
        />
        <div
          className="absolute inset-0"
          style={{ background: "rgba(30,30,30,0.30)" }}
        />
      </div>

      {/* ── SCROLLABLE CONTENT ──────────────────────────── */}
      <div className="relative z-10">

      {/* ── NAV ─────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-gray-100 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm font-bold"
              style={{ background: "linear-gradient(135deg, #0f766e, #0891b2)" }}
            >
              103
            </span>
            <span className="font-semibold text-gray-800">Apartment 103</span>
          </div>
          <nav className="hidden sm:flex items-center gap-6 text-sm text-gray-500">
            <GalleryButton />
            <a href="#" className="hover:text-teal-700 transition-colors">Amenities</a>
            <a href="#" className="hover:text-teal-700 transition-colors">Location</a>
            <a href="#" className="hover:text-teal-700 transition-colors">Reviews</a>
          </nav>
        </div>
      </header>

      {/* ── HERO ────────────────────────────────────────── */}
      <div className="min-h-[calc(100vh-4rem)]">
        <div className="max-w-7xl mx-auto px-6 py-16 lg:py-20">
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_480px] gap-12 items-start">
            {/* Left — apartment info */}
            <div className="text-white">
              <div className="flex flex-wrap items-center gap-2 mb-5">
                <span className="flex items-center gap-1.5 bg-white/20 backdrop-blur-sm text-white text-xs font-medium px-3 py-1.5 rounded-full">
                  <span>📍</span>
                  <span>Unterterzen, Switzerland</span>
                </span>
                <span className="flex items-center gap-1 bg-amber-400/90 text-amber-900 text-xs font-semibold px-3 py-1.5 rounded-full">
                  ★ 4.9 · 48 reviews
                </span>
              </div>

              <h1 className="text-4xl lg:text-5xl font-bold leading-tight mb-4">
                Your perfect<br />
                <span className="text-cyan-200">holiday escape</span>
              </h1>

              <p className="text-lg text-teal-100 mb-8 max-w-md leading-relaxed">
                A cosy apartment nestled between the mountains and Lake Walensee.
                Stunning alpine scenery, ski slopes and a lakeshore beach right
                on your doorstep.
              </p>

              {/* Feature tags */}
              <div className="flex flex-wrap gap-2">
                {FEATURES.map((f) => (
                  <span
                    key={f.label}
                    className="flex items-center gap-1.5 bg-white/15 backdrop-blur-sm px-3 py-1.5 rounded-full text-sm text-white"
                  >
                    <span>{f.icon}</span>
                    <span>{f.label}</span>
                  </span>
                ))}
              </div>

            </div>

            {/* Right — booking widget */}
            <div className="lg:sticky lg:top-20">
              <BookingWidget />
            </div>
          </div>
        </div>
      </div>

      {/* ── ABOUT / HIGHLIGHTS ──────────────────────────── */}
      <section className="max-w-7xl mx-auto px-6 py-16">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {[
            {
              icon: "🚂",
              title: "45 min from Zurich",
              desc: "Easy train connection to Zurich city centre — perfect for a day trip or a late arrival.",
            },
            {
              icon: "⛷️",
              title: "5 min to the ski lift",
              desc: "Hit the slopes in minutes. Flumserberg ski resort is right above the village.",
            },
            {
              icon: "🏖",
              title: "2 min to the beach",
              desc: "Lake Walensee's crystal-clear waters are a 2-minute stroll from the apartment.",
            },
          ].map((card) => (
            <div
              key={card.title}
              className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100"
            >
              <div className="text-3xl mb-3">{card.icon}</div>
              <h3 className="font-semibold text-gray-900 mb-2">{card.title}</h3>
              <p className="text-gray-500 text-sm leading-relaxed">{card.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── FOOTER ──────────────────────────────────────── */}
      <footer className="border-t border-gray-200 bg-white">
        <div className="max-w-7xl mx-auto px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-gray-400">
          <span>© 2026 Apartment 103. All rights reserved.</span>
          <div className="flex gap-6">
            <a href="#" className="hover:text-teal-700 transition-colors">Privacy</a>
            <a href="#" className="hover:text-teal-700 transition-colors">Terms</a>
            <a href="#" className="hover:text-teal-700 transition-colors">Contact</a>
          </div>
        </div>
      </footer>
      </div>{/* end scrollable content */}
    </div>
  );
}
