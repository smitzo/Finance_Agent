import { useEffect, useState } from "react";
import { useAuth } from "./context/AuthContext";
import { AuthScreen } from "./features/auth/AuthScreen";
import { AppLayout } from "./layout/AppLayout";
import { CompanyPage } from "./pages/CompanyPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PartnerPage } from "./pages/PartnerPage";
import { BillsPage } from "./pages/BillsPage";
import { ReviewQueuePage } from "./pages/ReviewQueuePage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { DemoPage } from "./pages/DemoPage";

export type Page = "overview" | "demo" | "bills" | "reviews" | "analytics" | "company" | "partner";

export function App() {
  const { session } = useAuth();
  const [page, setPage] = useState<Page>("overview");
  const [publicDemo, setPublicDemo] = useState(() => window.location.hash === "#demo");

  useEffect(() => {
    const syncHash = () => setPublicDemo(window.location.hash === "#demo");
    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, []);

  function openPublicDemo() {
    window.location.hash = "demo";
    setPublicDemo(true);
  }

  function closePublicDemo() {
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
    setPublicDemo(false);
  }

  if (!session) {
    return publicDemo ? <DemoPage standalone onBack={closePublicDemo} /> : <AuthScreen onOpenDemo={openPublicDemo} />;
  }

  return (
    <AppLayout activePage={page} onNavigate={(nextPage) => setPage(nextPage as Page)}>
      <>
        {page === "overview" ? <OverviewPage onNavigate={setPage} /> : null}
        {page === "demo" ? <DemoPage /> : null}
        {page === "bills" ? <BillsPage /> : null}
        {page === "reviews" ? <ReviewQueuePage /> : null}
        {page === "analytics" ? <AnalyticsPage /> : null}
        {page === "company" ? <CompanyPage /> : null}
        {page === "partner" ? <PartnerPage /> : null}
      </>
    </AppLayout>
  );
}
