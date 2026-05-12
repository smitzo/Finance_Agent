import { BarChart3, Building2, LogOut, Moon, ShieldCheck, Sun, Truck } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { Button } from "../components/ui/Button";
import { ToastViewport } from "../components/common/ToastViewport";

type AppLayoutProps = {
  activePage: string;
  onNavigate: (page: string) => void;
  children: React.ReactNode;
};

const navItems = [
  { id: "overview", label: "Overview", icon: BarChart3 },
  { id: "company", label: "Company", icon: Building2 },
  { id: "partner", label: "CA Partner", icon: ShieldCheck },
];

export function AppLayout({ activePage, onNavigate, children }: AppLayoutProps) {
  const { session, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  return (
    <main className="min-h-screen bg-slate-50 text-slate-950 transition-colors dark:bg-zinc-950 dark:text-white">
      <div className="grid min-h-screen lg:grid-cols-[280px_1fr]">
        <aside className="border-b border-slate-200 bg-white/80 p-5 backdrop-blur dark:border-white/10 dark:bg-zinc-950/80 lg:border-b-0 lg:border-r">
          <div className="flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-teal-600 text-white dark:bg-teal-400 dark:text-zinc-950">
              <Truck className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-teal-600 dark:text-teal-300">Freight AI</p>
              <h1 className="font-semibold">Operating System</h1>
            </div>
          </div>

          <nav className="mt-8 grid gap-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = activePage === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  className={`flex items-center gap-3 rounded-xl px-3 py-3 text-left text-sm font-medium transition ${
                    active
                      ? "bg-slate-950 text-white dark:bg-white dark:text-zinc-950"
                      : "text-slate-600 hover:bg-slate-100 dark:text-zinc-300 dark:hover:bg-white/10"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </button>
              );
            })}
          </nav>
        </aside>

        <section className="min-w-0">
          <header className="flex items-center justify-between border-b border-slate-200 bg-white/70 px-6 py-4 backdrop-blur dark:border-white/10 dark:bg-zinc-950/70">
            <div>
              <p className="text-sm text-slate-500 dark:text-zinc-400">Tenant</p>
              <h2 className="font-semibold">{session?.tenantId}</h2>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                onClick={toggleTheme}
                icon={theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              >
                {theme === "dark" ? "Light" : "Dark"}
              </Button>
              <Button variant="ghost" onClick={logout} icon={<LogOut className="h-4 w-4" />}>
                Logout
              </Button>
            </div>
          </header>
          <div className="p-6">{children}</div>
        </section>
      </div>
      <ToastViewport />
    </main>
  );
}
