import { BarChart3, Database, FolderKanban, KeyRound, LayoutDashboard, LogOut, Microscope } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "@/hooks/use-auth";
import { clsx } from "@/lib/utils";

const navigation = [
  { to: "/overview", label: "Overview", icon: LayoutDashboard },
  { to: "/experiments", label: "Experiments", icon: Microscope },
  { to: "/datasets", label: "Datasets", icon: Database },
  { to: "/repositories", label: "Repositories", icon: FolderKanban },
  { to: "/account", label: "Account", icon: KeyRound },
];

export function AppShell() {
  const { logout, user } = useAuth();

  return (
    <div className="min-h-screen bg-transparent px-3 py-3 sm:px-5 lg:px-6">
      <div className="mx-auto grid min-h-[calc(100vh-1.5rem)] max-w-[1880px] gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="xl:sticky xl:top-3 xl:h-[calc(100vh-1.5rem)] xl:overflow-y-auto rounded-[32px] border border-border/80 bg-ink px-6 py-8 text-paper shadow-card">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/10">
              <BarChart3 className="h-6 w-6" />
            </div>
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.28em] text-paper/60">Control Plane</p>
              <p className="text-lg font-semibold">Dashboard</p>
            </div>
          </div>

          <nav className="mt-10 space-y-2">
            {navigation.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition",
                    isActive ? "bg-white/12 text-white" : "text-paper/70 hover:bg-white/8 hover:text-white",
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {label}
              </NavLink>
            ))}
          </nav>

          <div className="mt-10 rounded-[24px] border border-white/10 bg-white/5 p-5">
            <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-paper/55">Signed in as</p>
            <p className="mt-2 break-all text-sm font-semibold">{user?.email}</p>
          </div>

          <button
            onClick={logout}
            className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-white/12 bg-white/5 px-4 py-3 text-sm font-semibold text-paper/85 transition hover:border-white/30 hover:bg-white/10 hover:text-white"
            type="button"
          >
            <LogOut className="h-4 w-4" />
            Log out
          </button>
        </aside>

        <main className="min-w-0 rounded-[32px] border border-border/80 bg-white/55 p-5 shadow-card backdrop-blur sm:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
