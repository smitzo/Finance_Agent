import { useAuth } from "./context/AuthContext";
import { AuthScreen } from "./features/auth/AuthScreen";
import { AppLayout } from "./layout/AppLayout";

export function App() {
  const { session } = useAuth();

  if (!session) {
    return <AuthScreen />;
  }

  return (
    <AppLayout activePage="overview" onNavigate={() => undefined}>
      <div className="rounded-2xl border border-slate-200 bg-white p-6 dark:border-white/10 dark:bg-white/[0.05]">
        Dashboard workspace loading.
      </div>
    </AppLayout>
  );
}
