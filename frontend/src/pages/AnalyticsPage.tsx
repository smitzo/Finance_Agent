import { Activity, ArrowUpRight, BarChart3, CircleDollarSign, Clock3, ShieldCheck, Sparkles, Target } from "lucide-react";
import { useEffect, useState } from "react";
import { BreakdownList } from "../components/dashboard/BreakdownList";
import { StatCard } from "../components/dashboard/StatCard";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import { formatCurrency, formatPercent } from "../lib/format";
import type { FreightBill, Metrics } from "../types";

export function AnalyticsPage() {
  const { session } = useAuth();
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [bills, setBills] = useState<FreightBill[]>([]);

  useEffect(() => {
    if (!session) return;
    Promise.all([api.metrics(session), api.bills(session)]).then(([nextMetrics, nextBills]) => {setMetrics(nextMetrics); setBills(nextBills);});
  }, [session?.tenantId]);

  const exposure = bills.reduce((sum, bill) => sum + bill.total_amount, 0);
  const automated = bills.filter((bill) => bill.status === "approved").length;
  const automationRate = bills.length ? automated / bills.length : 0;
  const laneTotals = bills.reduce<Record<string, number>>((result, bill) => ({...result, [bill.lane]: (result[bill.lane] ?? 0) + bill.total_amount}), {});
  const largestLane = Math.max(1, ...Object.values(laneTotals));

  return <div className="grid gap-6"><header><p className="text-xs font-bold uppercase tracking-[0.2em] text-emerald-700 dark:text-[#d8ff5f]">Performance intelligence</p><h1 className="mt-2 text-3xl font-semibold tracking-[-0.03em]">Audit analytics</h1><p className="mt-2 text-sm text-slate-500 dark:text-white/45">Understand workflow health, decision quality and financial exposure.</p></header>
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4"><StatCard label="Audited exposure" value={formatCurrency(exposure)} detail="Across loaded freight bills" icon={<CircleDollarSign className="h-5 w-5" />} /><StatCard label="Automation rate" value={formatPercent(automationRate)} detail="Approved without review" icon={<Sparkles className="h-5 w-5" />} /><StatCard label="Average confidence" value={formatPercent(metrics?.avg_confidence_score)} detail="Across agent decisions" icon={<Target className="h-5 w-5" />} /><StatCard label="Review backlog" value={metrics?.by_status.awaiting_review ?? 0} detail="Human decisions pending" icon={<Clock3 className="h-5 w-5" />} /></section>
    <section className="grid gap-6 xl:grid-cols-[1.35fr_.65fr]"><Card><CardHeader><div className="flex items-center justify-between"><div><h2 className="font-semibold">Exposure by lane</h2><p className="mt-1 text-sm text-slate-400">Total billed value represented in this tenant.</p></div><span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-50 text-emerald-700 dark:bg-emerald-400/10"><BarChart3 className="h-5 w-5" /></span></div></CardHeader><CardBody className="space-y-5">{Object.entries(laneTotals).sort((a,b) => b[1]-a[1]).slice(0,7).map(([lane,value]) => <div key={lane}><div className="mb-2 flex items-center justify-between text-sm"><span className="font-medium">{lane}</span><span className="font-semibold">{formatCurrency(value)}</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-white/10"><div className="h-full rounded-full bg-gradient-to-r from-[#173b33] to-emerald-400" style={{width:`${Math.max(7,(value/largestLane)*100)}%`}} /></div></div>)}{!bills.length ? <p className="py-16 text-center text-sm text-slate-400">Load demo data to populate lane analytics.</p> : null}</CardBody></Card><div className="grid gap-6"><BreakdownList title="Workflow stages" subtitle="Where every bill sits now." values={metrics?.by_status ?? {}} /><BreakdownList title="Decision mix" subtitle="Agent and reviewer outcomes." values={metrics?.by_decision ?? {}} /></div></section>
    <Card className="overflow-hidden border-0 bg-[#102e27] text-white"><CardBody className="grid gap-6 p-7 md:grid-cols-[1fr_auto] md:items-center"><div className="flex gap-4"><span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-[#d8ff5f] text-[#07110f]"><ShieldCheck className="h-6 w-6" /></span><div><h2 className="text-lg font-semibold">Confidence remains a routing signal, not a financial fact.</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-white/50">Exact totals, rates, dates and weights stay deterministic. Model confidence only governs when ambiguity should be escalated to a reviewer.</p></div></div><div className="flex items-center gap-2 text-xs font-medium text-[#d8ff5f]">View decision policy <ArrowUpRight className="h-4 w-4" /></div></CardBody></Card>
  </div>;
}
