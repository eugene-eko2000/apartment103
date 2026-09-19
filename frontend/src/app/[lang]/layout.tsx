import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Geist, Geist_Mono } from "next/font/google";
import "../globals.css";
import { locales } from "@/lib/i18n-config";
import { CurrencyProvider } from "@/lib/currency-context";
import { CookieConsentProvider } from "@/lib/cookie-consent-context";
import { ThemeProvider, THEME_INIT_SCRIPT } from "@/lib/theme-context";
import { OverlayProvider } from "@/lib/overlay-context";
import CookieConsentBanner from "@/components/CookieConsentBanner";
import GuestPreferenceSync from "@/components/GuestPreferenceSync";
import { getDictionary, hasLocale } from "./dictionaries";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export async function generateStaticParams() {
  return locales.map((lang) => ({ lang }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ lang: string }>;
}): Promise<Metadata> {
  const { lang } = await params;
  if (!hasLocale(lang)) return {};

  const dict = await getDictionary(lang);
  return {
    title: dict.meta.title,
    description: dict.meta.description,
  };
}

export default async function RootLayout({
  children,
  params,
}: Readonly<{
  children: React.ReactNode;
  params: Promise<{ lang: string }>;
}>) {
  const { lang } = await params;
  if (!hasLocale(lang)) notFound();

  const dict = await getDictionary(lang);

  return (
    <html
      lang={lang}
      data-theme="light"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col">
        <ThemeProvider>
          <CookieConsentProvider>
            <CurrencyProvider>
              <GuestPreferenceSync />
              {/* Owns the gallery/amenities/location views and renders the one
                  that is open — above the page, but inside the same providers,
                  since each view carries the site header and footer. */}
              <OverlayProvider lang={lang} dict={dict}>{children}</OverlayProvider>
            </CurrencyProvider>
            <CookieConsentBanner dict={dict.cookieConsent} />
          </CookieConsentProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
