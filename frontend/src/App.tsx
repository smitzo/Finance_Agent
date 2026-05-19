import { useState } from "react";
import { useAuth } from "./context/AuthContext";
import { AuthScreen } from "./features/auth/AuthScreen";
import { AppLayout } from "./layout/AppLayout";

type Page = "overview" | "company" | "partner";

export function App() {
  const { session } = useAuth();
  const [page, setPage] = useState<Page>("overview");

  if (!session) {
    return <AuthScreen />;
  }

  return (
    <AppLayout activePage={page} onNavigate={(nextPage) => setPage(nextPage as Page)}>
      <div className="rounded-2xl border border-slate-200 bg-white p-6 dark:border-white/10 dark:bg-white/[0.05]">
        {page === "overview" ? "Overview workspace loading." : null}
        {page === "company" ? "Company workspace loading." : null}
        {page === "partner" ? "Partner workspace loading." : null}
      </div>
    </AppLayout>
  );
}
