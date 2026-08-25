"use client";

import { useState } from "react";
import { useAdminAuth } from "@/lib/admin-auth";
import AdminLogin from "@/components/admin/AdminLogin";
import AdminShell, { type AdminTab } from "@/components/admin/AdminShell";
import AdminsPanel from "@/components/admin/resources/AdminsPanel";
import GuestsPanel from "@/components/admin/resources/GuestsPanel";
import CancellationPoliciesPanel from "@/components/admin/resources/CancellationPoliciesPanel";
import PlansPanel from "@/components/admin/resources/PlansPanel";
import PricesPanel from "@/components/admin/resources/PricesPanel";
import PromotionsPanel from "@/components/admin/resources/PromotionsPanel";
import BookingsPanel from "@/components/admin/resources/BookingsPanel";
import CalendarPanel from "@/components/admin/resources/CalendarPanel";
import ClosuresPanel from "@/components/admin/resources/ClosuresPanel";
import SyncCalendarsPanel from "@/components/admin/resources/SyncCalendarsPanel";
import PhotosPanel from "@/components/admin/resources/PhotosPanel";

export default function AdminPage() {
  const { session, ready } = useAdminAuth();
  const [tab, setTab] = useState<AdminTab>("bookings");

  if (!ready) return null;
  if (!session) return <AdminLogin />;

  return (
    <AdminShell activeTab={tab} onTabChange={setTab}>
      {tab === "bookings" && <BookingsPanel />}
      {tab === "calendar" && <CalendarPanel />}
      {tab === "closures" && <ClosuresPanel />}
      {tab === "sync-calendars" && <SyncCalendarsPanel />}
      {tab === "guests" && <GuestsPanel />}
      {tab === "plans" && <PlansPanel />}
      {tab === "prices" && <PricesPanel />}
      {tab === "promotions" && <PromotionsPanel />}
      {tab === "cancellation-policies" && <CancellationPoliciesPanel />}
      {tab === "photos" && <PhotosPanel />}
      {tab === "admins" && <AdminsPanel />}
    </AdminShell>
  );
}
