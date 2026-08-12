import { useState } from "react";
import { useAuth } from "./context/AuthContext";
import { AuthScreen } from "./features/auth/AuthScreen";
import { AppLayout } from "./layout/AppLayout";
import { CompanyPage } from "./pages/CompanyPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PartnerPage } from "./pages/PartnerPage";
import { BillsPage } from "./pages/BillsPage";
import { ReviewQueuePage } from "./pages/ReviewQueuePage";
import { AnalyticsPage } from "./pages/AnalyticsPage";

export type Page = "overview" | "bills" | "reviews" | "analytics" | "company" | "partner";

export function App() {
  const { session } = useAuth();
  const [page, setPage] = useState<Page>("overview");

  if (!session) {
    return <AuthScreen />;
  }

  return (
    <AppLayout activePage={page} onNavigate={(nextPage) => setPage(nextPage as Page)}>
      <>
        {page === "overview" ? <OverviewPage onNavigate={setPage} /> : null}
        {page === "bills" ? <BillsPage /> : null}
        {page === "reviews" ? <ReviewQueuePage /> : null}
        {page === "analytics" ? <AnalyticsPage /> : null}
        {page === "company" ? <CompanyPage /> : null}
        {page === "partner" ? <PartnerPage /> : null}
      </>
    </AppLayout>
  );
}
