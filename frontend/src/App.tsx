import { useState } from "react";
import { useAuth } from "./context/AuthContext";
import { AuthScreen } from "./features/auth/AuthScreen";
import { AppLayout } from "./layout/AppLayout";
import { CompanyPage } from "./pages/CompanyPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PartnerPage } from "./pages/PartnerPage";

type Page = "overview" | "company" | "partner";

export function App() {
  const { session } = useAuth();
  const [page, setPage] = useState<Page>("overview");

  if (!session) {
    return <AuthScreen />;
  }

  return (
    <AppLayout activePage={page} onNavigate={(nextPage) => setPage(nextPage as Page)}>
      <>
        {page === "overview" ? <OverviewPage /> : null}
        {page === "company" ? <CompanyPage /> : null}
        {page === "partner" ? <PartnerPage /> : null}
      </>
    </AppLayout>
  );
}
