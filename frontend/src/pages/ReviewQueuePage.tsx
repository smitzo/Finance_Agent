import { AlertTriangle, ArrowRight, CheckCircle2, ClipboardCheck, Clock3, FileWarning, RefreshCw, ShieldAlert, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardBody } from "../components/ui/Card";
import { Textarea } from "../components/ui/Input";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { api } from "../lib/api";
import { formatCurrency, formatPercent } from "../lib/format";
import type { FreightBill } from "../types";

export function ReviewQueuePage() {
  const { session } = useAuth();
  const { showToast } = useToast();
  const [bills, setBills] = useState<FreightBill[]>([]);
  const [selected, setSelected] = useState<FreightBill | null>(null);
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  async function refresh() {
    if (!session) return;
    setLoading(true);
    try {
      const next = await api.reviewQueue(session);
      setBills(next);
      setSelected((current) => next.find((bill) => bill.id === current?.id) ?? next[0] ?? null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh().catch(() => showToast("Could not load review queue.", "error")); }, [session?.tenantId]);

  async function decide(decision: "approve" | "dispute" | "reject") {
    if (!session || !selected) return;
    setSubmitting(true);
    try {
      await api.submitReview(session, selected.id, decision, notes);
      showToast(`${selected.id} queued with decision: ${decision}.`, "success");
      setNotes("");
      await refresh();
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Review could not be submitted.", "error");
    } finally {
      setSubmitting(false);
    }
  }

  const findings = selected?.evidence?.findings ?? [];

  return (
    <div className="grid gap-6">
      <header className="flex flex-col justify-between gap-4 md:flex-row md:items-end"><div><div className="flex items-center gap-2"><p className="text-xs font-bold uppercase tracking-[0.2em] text-amber-700 dark:text-amber-300">Human control</p>{bills.length ? <Badge tone="warn">{bills.length} waiting</Badge> : null}</div><h1 className="mt-2 text-3xl font-semibold tracking-[-0.03em]">Review queue</h1><p className="mt-2 text-sm text-slate-500 dark:text-white/45">Resolve the small set of exceptions that need accountable human judgment.</p></div><Button variant="secondary" onClick={refresh} icon={<RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />}>Refresh queue</Button></header>

      {!bills.length && !loading ? <Card><CardBody className="grid min-h-[420px] place-items-center text-center"><div><span className="mx-auto grid h-16 w-16 place-items-center rounded-3xl bg-emerald-50 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300"><ClipboardCheck className="h-7 w-7" /></span><h2 className="mt-5 text-xl font-semibold">Your review queue is clear</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">No bills currently need manual attention. The worker will pause new low-confidence cases here.</p></div></CardBody></Card> : null}

      {bills.length ? <div className="grid gap-5 xl:grid-cols-[380px_1fr]">
        <Card className="overflow-hidden self-start"><div className="border-b border-slate-200 px-5 py-4 dark:border-white/10"><h2 className="font-semibold">Exception inbox</h2><p className="mt-1 text-xs text-slate-400">Oldest cases appear first.</p></div><div className="max-h-[720px] overflow-y-auto">{bills.map((bill) => <button key={bill.id} onClick={() => {setSelected(bill); setNotes("");}} className={`w-full border-b border-slate-100 p-4 text-left transition last:border-0 dark:border-white/5 ${selected?.id === bill.id ? "bg-amber-50 dark:bg-amber-400/[0.07]" : "hover:bg-slate-50 dark:hover:bg-white/[0.03]"}`}><div className="flex items-start justify-between gap-3"><div><p className="font-semibold">{bill.id}</p><p className="mt-1 text-xs text-slate-400">{bill.carrier_name}</p></div><span className="flex items-center gap-1 text-[10px] text-amber-700 dark:text-amber-300"><Clock3 className="h-3 w-3" /> waiting</span></div><div className="mt-4 flex items-end justify-between"><div><p className="text-[10px] uppercase tracking-wide text-slate-400">Exposure</p><p className="mt-1 font-semibold">{formatCurrency(bill.total_amount)}</p></div><div className="text-right"><p className="text-[10px] uppercase tracking-wide text-slate-400">Confidence</p><p className="mt-1 text-sm font-semibold">{formatPercent(bill.confidence_score)}</p></div></div></button>)}</div></Card>

        {selected ? <Card className="overflow-hidden"><div className="border-b border-slate-200 bg-gradient-to-r from-amber-50 to-white p-6 dark:border-white/10 dark:from-amber-400/[0.06] dark:to-transparent"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start"><div><div className="flex items-center gap-2"><Badge tone="warn">Needs decision</Badge><span className="text-xs text-slate-400">{selected.bill_number}</span></div><h2 className="mt-3 text-2xl font-semibold">{selected.id}</h2><p className="mt-1 text-sm text-slate-500">{selected.carrier_name} · {selected.lane}</p></div><div className="text-left sm:text-right"><p className="text-xs text-slate-400">Bill exposure</p><p className="mt-1 text-2xl font-semibold">{formatCurrency(selected.total_amount)}</p></div></div></div><CardBody className="grid gap-6">
          <div className="grid gap-3 sm:grid-cols-3">{[["Agent decision",selected.decision?.replaceAll("_", " ") ?? "flag"],["Confidence",formatPercent(selected.confidence_score)],["Bill date",selected.bill_date ?? "--"]].map(([label,value]) => <div key={label} className="rounded-2xl bg-slate-50 p-4 dark:bg-white/5"><p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">{label}</p><p className="mt-2 text-sm font-semibold capitalize">{value}</p></div>)}</div>
          <div><h3 className="flex items-center gap-2 text-sm font-semibold"><ShieldAlert className="h-4 w-4 text-amber-600" /> Why this bill paused</h3><p className="mt-3 rounded-2xl border border-amber-200 bg-amber-50/60 p-4 text-sm leading-6 text-amber-950 dark:border-amber-400/20 dark:bg-amber-400/[0.06] dark:text-amber-100">{selected.decision_reason || "Agent confidence fell below the automatic action threshold. Review the findings and shipment evidence before deciding."}</p></div>
          <div><div className="flex items-center justify-between"><h3 className="text-sm font-semibold">Validation findings</h3><span className="text-xs text-slate-400">{findings.length} checks surfaced</span></div><div className="mt-3 grid gap-2">{findings.map((finding, index) => <div key={`${finding.code}-${index}`} className="flex items-start gap-3 rounded-2xl border border-slate-200 p-4 dark:border-white/10"><span className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-xl ${finding.severity === "error" ? "bg-rose-50 text-rose-600 dark:bg-rose-400/10" : "bg-amber-50 text-amber-600 dark:bg-amber-400/10"}`}>{finding.severity === "error" ? <XCircle className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}</span><div><div className="flex items-center gap-2"><p className="text-sm font-semibold">{finding.code?.replaceAll("_", " ") ?? "Validation exception"}</p><Badge tone={finding.severity === "error" ? "danger" : "warn"}>{finding.severity ?? "review"}</Badge></div><p className="mt-1 text-xs leading-5 text-slate-500">{finding.message}</p></div></div>)}{!findings.length ? <div className="rounded-2xl border border-dashed border-slate-200 p-5 text-sm text-slate-400 dark:border-white/10"><FileWarning className="mb-2 h-5 w-5" />No structured findings were persisted. Use the rationale and source records to decide.</div> : null}</div></div>
          <Textarea label="Reviewer notes" hint="Your note is written to the audit trail." value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="What did you verify, and why is this the right decision?" />
          <div className="flex flex-col justify-between gap-3 border-t border-slate-200 pt-5 dark:border-white/10 sm:flex-row sm:items-center"><p className="text-xs text-slate-400">Submitting resumes the durable agent thread.</p><div className="flex flex-wrap gap-2"><Button disabled={submitting} variant="danger" onClick={() => decide("reject")} icon={<XCircle className="h-4 w-4" />}>Reject</Button><Button disabled={submitting} variant="secondary" onClick={() => decide("dispute")} icon={<AlertTriangle className="h-4 w-4" />}>Dispute</Button><Button disabled={submitting} onClick={() => decide("approve")} icon={<CheckCircle2 className="h-4 w-4" />}>Approve & resume <ArrowRight className="h-4 w-4" /></Button></div></div>
        </CardBody></Card> : null}
      </div> : null}
    </div>
  );
}
