import { Activity, BarChart3, Bell, Building2, ChevronDown, CircleHelp, ClipboardCheck, FileText, FlaskConical, LogOut, Moon, Search, ShieldCheck, Sparkles, Sun, Truck } from "lucide-react";
import type { ReactNode } from "react";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { Button } from "../components/ui/Button";
import { ToastViewport } from "../components/common/ToastViewport";

type AppLayoutProps = {
  activePage: string;
  onNavigate: (page: string) => void;
  children: ReactNode;
};

const navItems = [
  { id: "overview", label: "Overview", icon: BarChart3 },
  { id: "demo", label: "Interactive demo", icon: FlaskConical, badge: "Static" },
  { id: "bills", label: "Freight bills", icon: FileText },
  { id: "reviews", label: "Review queue", icon: ClipboardCheck, badge: "Live" },
  { id: "analytics", label: "Analytics", icon: Activity },
  { id: "company", label: "Company", icon: Building2 },
  { id: "partner", label: "Audit partner", icon: ShieldCheck },
];

export function AppLayout({ activePage, onNavigate, children }: AppLayoutProps) {
  const { session, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  return (
    <main className="min-h-screen bg-[#f4f7f6] text-slate-950 transition-colors dark:bg-[#07100e] dark:text-white">
      <div className="grid min-h-screen lg:grid-cols-[264px_1fr]">
        <aside className="flex flex-col border-b border-slate-200 bg-[#07110f] p-4 text-white dark:border-white/10 lg:sticky lg:top-0 lg:h-screen lg:border-b-0 lg:border-r lg:border-white/10">
          <div className="flex items-center gap-3 px-2 py-2">
            <div className="relative grid h-10 w-10 place-items-center rounded-xl bg-[#d8ff5f] text-[#07110f] shadow-[0_0_30px_rgba(216,255,95,.18)]">
              <Truck className="h-5 w-5" />
              <span className="absolute -right-1 -top-1 h-3 w-3 rounded-full border-2 border-[#07110f] bg-emerald-400" />
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-[#d8ff5f]">FreightFlow</p>
              <h1 className="font-semibold tracking-tight">AI Control Tower</h1>
            </div>
          </div>

          <div className="mt-6 rounded-xl border border-white/10 bg-white/[0.06] p-3">
            <div className="flex items-center gap-2 text-xs text-white/55"><Sparkles className="h-3.5 w-3.5 text-[#d8ff5f]" /> Agent workspace</div>
            <div className="mt-2 flex items-center justify-between text-sm font-medium"><span>{session?.tenantId}</span><ChevronDown className="h-4 w-4 text-white/40" /></div>
          </div>

          <p className="mb-2 mt-7 px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-white/35">Workspace</p>
          <nav className="grid gap-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = activePage === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-medium transition ${
                    active
                      ? "bg-white text-[#07110f] shadow-lg shadow-black/10"
                      : "text-white/60 hover:bg-white/[0.07] hover:text-white"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  <span className="flex-1">{item.label}</span>
                  {item.badge ? <span className="rounded-full bg-[#d8ff5f]/15 px-2 py-0.5 text-[10px] text-[#d8ff5f]">{item.badge}</span> : null}
                </button>
              );
            })}
          </nav>

          <div className="mt-auto hidden pt-6 lg:block">
            <div className="rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.08] to-transparent p-4">
              <div className="flex items-center gap-2 text-xs font-medium text-emerald-300"><span className="h-2 w-2 rounded-full bg-emerald-400" /> Systems operational</div>
              <p className="mt-2 text-xs leading-5 text-white/45">API, worker queue, graph and database are connected.</p>
            </div>
            <button className="mt-3 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-white/55 hover:bg-white/[0.06] hover:text-white"><CircleHelp className="h-4 w-4" /> Help & documentation</button>
          </div>
        </aside>

        <section className="min-w-0">
          <header className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-200/80 bg-white/85 px-5 py-3 backdrop-blur-xl dark:border-white/10 dark:bg-[#07100e]/85 md:px-7">
            <div className="hidden min-w-0 flex-1 items-center md:flex">
              <Search className="h-4 w-4 text-slate-400" />
              <input className="w-full max-w-md bg-transparent px-3 py-2 text-sm outline-none placeholder:text-slate-400" placeholder="Search bills, carriers or shipment refs..." />
            </div>
            <div className="flex items-center gap-2">
              <span className="hidden rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-300 sm:inline-flex">Live operations</span>
              <Button
                variant="ghost"
                className="w-10 px-0"
                onClick={toggleTheme}
                aria-label="Toggle color theme"
              >
                {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </Button>
              <Button variant="ghost" className="w-10 px-0" aria-label="Notifications"><Bell className="h-4 w-4" /></Button>
              <div className="mx-1 h-7 w-px bg-slate-200 dark:bg-white/10" />
              <button onClick={logout} className="flex items-center gap-2 rounded-xl p-1.5 pr-2 text-left hover:bg-slate-100 dark:hover:bg-white/10" title="Sign out">
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-[#173b33] text-xs font-bold text-[#d8ff5f]">{session?.username.slice(0, 2).toUpperCase()}</span>
                <span className="hidden text-xs sm:block"><strong className="block font-semibold">{session?.username}</strong><span className="text-slate-400">Finance admin</span></span>
                <LogOut className="ml-1 h-3.5 w-3.5 text-slate-400" />
              </button>
            </div>
          </header>
          <div className="mx-auto max-w-[1600px] p-4 md:p-7">{children}</div>
        </section>
      </div>
      <ToastViewport />
    </main>
  );
}
