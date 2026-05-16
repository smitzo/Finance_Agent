import { AlertTriangle, CheckCircle2, DatabaseZap, FileText } from "lucide-react";
import { useEffect, useState } from "react";
import { TruckLoader } from "../components/common/TruckLoader";
import { BillTable } from "../components/dashboard/BillTable";
import { AnomalyRadar } from "../components/dashboard/AnomalyRadar";
import { BreakdownList } from "../components/dashboard/BreakdownList";
import { OnboardingProgress } from "../components/dashboard/OnboardingProgress";
import { StatCard } from "../components/dashboard/StatCard";
import { Button } from "../components/ui/Button";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { api } from "../lib/api";
import { formatPercent } from "../lib/format";
import type { FreightBill, Metrics } from "../types";

export function OverviewPage() {
  const { session } = useAuth();
  const { showToast } = useToast();
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [bills, setBills] = useState<FreightBill[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("Loading operating picture...");

  async function refresh() {
    if (!session) return;
    setLoading(true);
    setStatus("Loading operating picture...");
    const [nextMetrics, nextBills] = await Promise.all([api.metrics(session), api.bills(session)]);
    setMetrics(nextMetrics);
    setBills(nextBills);
    setStatus(`Updated ${new Date().toLocaleTimeString()}`);
    setLoading(false);
  }

  async function loadDemo() {
    if (!session) return;
    setStatus("Loading rich demo data...");
    await api.loadDemo(session);
    await refresh();
    showToast("Demo data loaded for this tenant.", "success");
  }

  async function deleteDemo() {
    if (!session) return;
    setStatus("Removing demo data...");
    await api.deleteDemo(session);
    await refresh();
    showToast("Demo data removed for this tenant.", "success");
  }

  useEffect(() => {
    refresh().catch((error) => {
      setStatus(error instanceof Error ? error.message : "Could not load dashboard");
      showToast("Could not load dashboard data.", "error");
      setLoading(false);
    });
  }, [session?.tenantId]);

  if (loading && !metrics) {
    return <TruckLoader />;
  }

  const byStatus = metrics?.by_status ?? {};

  return (
    <div className="grid gap-6">
      <section className="flex flex-col justify-between gap-4 rounded-3xl bg-slate-950 p-6 text-white shadow-glow dark:bg-white/[0.06] md:flex-row md:items-center">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.22em] text-teal-300">Control tower</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">Freight validation overview</h1>
          <p className="mt-2 text-sm text-slate-300">{status}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={refresh}>Refresh</Button>
          <Button variant="secondary" onClick={loadDemo} icon={<DatabaseZap className="h-4 w-4" />}>Use demo data</Button>
          <Button variant="danger" onClick={deleteDemo}>Delete demo</Button>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total bills" value={metrics?.total_bills ?? 0} detail="Across this tenant" icon={<FileText className="h-5 w-5" />} />
        <StatCard label="Awaiting review" value={byStatus.awaiting_review ?? 0} detail="Needs human decision" icon={<AlertTriangle className="h-5 w-5" />} />
        <StatCard label="Approved" value={byStatus.approved ?? 0} detail="Cleared workflow" icon={<CheckCircle2 className="h-5 w-5" />} />
        <StatCard label="Avg confidence" value={formatPercent(metrics?.avg_confidence_score)} detail="Agent score" icon={<DatabaseZap className="h-5 w-5" />} />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_360px]">
        <BillTable bills={bills} />
        <div className="grid gap-6">
          <OnboardingProgress
            steps={[
              { label: "Signed in", complete: Boolean(session) },
              { label: "Tenant selected", complete: Boolean(session?.tenantId) },
              { label: "Bills available", complete: Boolean(metrics?.total_bills) },
              { label: "Agent decisions present", complete: Boolean(Object.keys(metrics?.by_decision ?? {}).length) },
            ]}
          />
          <AnomalyRadar bills={bills} />
          <BreakdownList title="Status breakdown" subtitle="Current workflow stages." values={metrics?.by_status ?? {}} />
          <BreakdownList title="Decision breakdown" subtitle="Final agent outcomes." values={metrics?.by_decision ?? {}} />
        </div>
      </section>
    </div>
  );
}
