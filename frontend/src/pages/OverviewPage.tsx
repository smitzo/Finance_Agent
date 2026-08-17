import { AlertTriangle, ArrowRight, CheckCircle2, CircleDollarSign, DatabaseZap, FilePlus2, FileText, RefreshCw, Sparkles, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";
import type { Page } from "../App";
import { TruckLoader } from "../components/common/TruckLoader";
import { BillTable } from "../components/dashboard/BillTable";
import { BreakdownList } from "../components/dashboard/BreakdownList";
import { StatCard } from "../components/dashboard/StatCard";
import { Button } from "../components/ui/Button";
import { Card, CardBody } from "../components/ui/Card";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { api } from "../lib/api";
import { formatCurrency, formatPercent } from "../lib/format";
import type { FreightBill, Metrics } from "../types";

export function OverviewPage({ onNavigate }: { onNavigate: (page: Page) => void }) {
  const { session } = useAuth();
  const { showToast } = useToast();
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [bills, setBills] = useState<FreightBill[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("Synchronizing operations...");

  async function refresh() {
    if (!session) return;
    setLoading(true);
    const [nextMetrics, nextBills] = await Promise.all([api.metrics(session), api.bills(session, 12)]);
    setMetrics(nextMetrics);
    setBills(nextBills);
    setStatus(`Synced ${new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})}`);
    setLoading(false);
  }

  useEffect(() => { refresh().catch((error) => {setStatus(error instanceof Error ? error.message : "Could not load dashboard"); showToast("Could not load dashboard data.", "error"); setLoading(false);}); }, [session?.tenantId]);

  if (loading && !metrics) return <TruckLoader />;

  const byStatus = metrics?.by_status ?? {};
  const exposure = bills.reduce((sum, bill) => sum + bill.total_amount, 0);
  const completed = (byStatus.approved ?? 0) + (byStatus.disputed ?? 0) + (byStatus.rejected ?? 0);
  const completionRate = metrics?.total_bills ? completed / metrics.total_bills : 0;

  return <div className="grid gap-6">
    <section className="relative overflow-hidden rounded-[28px] bg-[#102e27] p-6 text-white shadow-[0_24px_70px_rgba(16,46,39,.18)] md:p-8"><div className="absolute right-0 top-0 h-64 w-64 translate-x-1/4 -translate-y-1/3 rounded-full bg-[#d8ff5f]/10 blur-3xl" /><div className="relative flex flex-col justify-between gap-7 lg:flex-row lg:items-end"><div><div className="flex items-center gap-2 text-xs font-semibold text-[#d8ff5f]"><Sparkles className="h-4 w-4" /> Friday operating brief</div><h1 className="mt-4 text-3xl font-semibold tracking-[-0.04em] md:text-4xl">Good evening, {session?.username}.</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-white/50">Your freight audit operation is live. {byStatus.awaiting_review ?? 0} bills need human attention and {byStatus.processing ?? 0} are being investigated by workers.</p><p className="mt-4 flex items-center gap-2 text-xs text-white/35"><span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse-soft" /> {status}</p></div><div className="flex flex-wrap gap-2"><Button onClick={() => onNavigate("bills")} className="bg-[#d8ff5f] text-[#07110f] shadow-none hover:bg-[#e5ff93] dark:bg-[#d8ff5f] dark:text-[#07110f]" icon={<FilePlus2 className="h-4 w-4" />}>Add freight bill</Button><Button onClick={refresh} className="border border-white/15 bg-white/10 text-white shadow-none hover:bg-white/15 dark:bg-white/10 dark:text-white" icon={<RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />}>Refresh</Button></div></div></section>

    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4"><StatCard label="Bills in workspace" value={metrics?.total_bills ?? 0} detail={`${Math.round(completionRate * 100)}% workflow completion`} icon={<FileText className="h-5 w-5" />} /><StatCard label="Reviewed exposure" value={formatCurrency(exposure)} detail="Recent 12 bills" icon={<CircleDollarSign className="h-5 w-5" />} /><StatCard label="Awaiting review" value={byStatus.awaiting_review ?? 0} detail="Human decisions required" icon={<AlertTriangle className="h-5 w-5" />} /><StatCard label="Average confidence" value={formatPercent(metrics?.avg_confidence_score)} detail="Current agent signal" icon={<TrendingUp className="h-5 w-5" />} /></section>

    <section className="grid gap-6 xl:grid-cols-[1fr_360px]"><div className="grid gap-6"><BillTable bills={bills} /><Card className="overflow-hidden"><CardBody className="flex flex-col justify-between gap-5 bg-gradient-to-r from-emerald-50 to-white md:flex-row md:items-center dark:from-emerald-400/[0.06] dark:to-transparent"><div className="flex items-center gap-4"><span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-emerald-100 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300"><CheckCircle2 className="h-6 w-6" /></span><div><h3 className="font-semibold">The audit trail is always on.</h3><p className="mt-1 text-sm text-slate-500">Open any bill to see ingestion, agent findings and reviewer decisions in order.</p></div></div><Button variant="secondary" onClick={() => onNavigate("bills")}>Browse bills <ArrowRight className="h-4 w-4" /></Button></CardBody></Card></div><div className="grid content-start gap-6"><Card className="overflow-hidden border-0 bg-[#102e27] text-white"><CardBody><div className="flex items-center justify-between"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#d8ff5f] text-[#07110f]"><DatabaseZap className="h-5 w-5" /></span><span className="rounded-full bg-white/10 px-2.5 py-1 text-[10px] text-emerald-200">No backend required</span></div><h2 className="mt-6 text-lg font-semibold">Show the complete audit flow.</h2><p className="mt-2 text-sm leading-6 text-white/45">Process a synthetic bill through simulated API, graph, rule, model, and persistence stages in the browser.</p><button onClick={() => onNavigate("demo")} className="mt-5 flex items-center gap-2 text-sm font-semibold text-[#d8ff5f]">Process demo data <ArrowRight className="h-4 w-4" /></button></CardBody></Card><BreakdownList title="Workflow stages" subtitle="Live tenant distribution." values={metrics?.by_status ?? {}} /><BreakdownList title="Decision outcomes" subtitle="Agent and human results." values={metrics?.by_decision ?? {}} /><button onClick={() => onNavigate("reviews")} className="flex items-center justify-between rounded-2xl border border-amber-200 bg-amber-50 p-4 text-left transition hover:border-amber-300 dark:border-amber-400/20 dark:bg-amber-400/[0.06]"><div><p className="text-sm font-semibold text-amber-900 dark:text-amber-100">Open review queue</p><p className="mt-1 text-xs text-amber-700/70 dark:text-amber-200/50">{byStatus.awaiting_review ?? 0} exceptions waiting</p></div><ArrowRight className="h-4 w-4 text-amber-700" /></button></div></section>
  </div>;
}
