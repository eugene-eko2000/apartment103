import { notFound } from "next/navigation";
import MyBookingsView from "@/components/MyBookingsView";
import { getDictionary, hasLocale } from "../dictionaries";

export default async function MyBookingsPage({
  params,
}: {
  params: Promise<{ lang: string }>;
}) {
  const { lang } = await params;
  if (!hasLocale(lang)) notFound();

  const dict = await getDictionary(lang);

  return <MyBookingsView dict={dict.myBookings} lang={lang} />;
}
