import { useAuth } from "./context/AuthContext";
import { AuthScreen } from "./features/auth/AuthScreen";

export function App() {
  const { session } = useAuth();

  if (!session) {
    return <AuthScreen />;
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-950 transition-colors dark:bg-zinc-950 dark:text-zinc-50">
      <div className="mx-auto flex min-h-screen max-w-7xl items-center justify-center px-6">
        <section className="w-full max-w-xl rounded-2xl border border-slate-200 bg-white p-8 shadow-xl dark:border-white/10 dark:bg-white/[0.04]">
          <p className="text-sm font-semibold uppercase tracking-[0.28em] text-teal-600 dark:text-teal-300">
            Freight AI OS
          </p>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight">
            Dashboard shell is ready.
          </h1>
          <p className="mt-4 text-slate-600 dark:text-zinc-300">
            Building the full React experience in small committed phases.
          </p>
        </section>
      </div>
    </main>
  );
}
