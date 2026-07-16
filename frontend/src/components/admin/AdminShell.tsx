"use client";

import { useAdminAuth } from "@/lib/admin-auth";

export type AdminTab = "bookings" | "guests" | "plans" | "prices" | "cancellation-policies" | "admins";

const TABS: { id: AdminTab; label: string }[] = [
  { id: "bookings", label: "Bookings" },
  { id: "guests", label: "Guests" },
  { id: "plans", label: "Plans" },
  { id: "prices", label: "Prices" },
  { id: "cancellation-policies", label: "Cancellation Policies" },
  { id: "admins", label: "Admins" },
];

export default function AdminShell({
  activeTab,
  onTabChange,
  children,
}: {
  activeTab: AdminTab;
  onTabChange: (tab: AdminTab) => void;
  children: React.ReactNode;
}) {
  const { logout } = useAdminAuth();

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <h1 className="text-base font-bold text-slate-800">apartment103 admin</h1>
          <button
            type="button"
            onClick={logout}
            className="text-sm font-medium text-slate-500 hover:text-slate-800 cursor-pointer"
          >
            Log out
          </button>
        </div>
        <nav className="max-w-6xl mx-auto px-6 flex gap-1 overflow-x-auto">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => onTabChange(tab.id)}
              className={`px-3 py-2.5 text-sm font-medium border-b-2 whitespace-nowrap cursor-pointer transition-colors ${
                activeTab === tab.id
                  ? "border-indigo-600 text-indigo-700"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </header>
      <main className="max-w-6xl mx-auto px-6 py-8">{children}</main>
    </div>
  );
}
