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
import BookingsPanel from "@/components/admin/resources/BookingsPanel";

export default function AdminPage() {
  const { session, ready } = useAdminAuth();
  const [tab, setTab] = useState<AdminTab>("bookings");

  if (!ready) return null;
  if (!session) return <AdminLogin />;

  return (
    <AdminShell activeTab={tab} onTabChange={setTab}>
      {tab === "bookings" && <BookingsPanel />}
      {tab === "guests" && <GuestsPanel />}
      {tab === "plans" && <PlansPanel />}
      {tab === "prices" && <PricesPanel />}
      {tab === "cancellation-policies" && <CancellationPoliciesPanel />}
      {tab === "admins" && <AdminsPanel />}
    </AdminShell>
  );
}
