import { ArrowDownUp, CalendarDays, CheckCircle2, ChevronRight, FilePlus2, FileSearch, Filter, RefreshCw, Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { api } from "../lib/api";
import { formatCurrency, formatPercent } from "../lib/format";
import type { AuditEvent, FreightBill, NewFreightBill } from "../types";

const emptyBill: NewFreightBill = {
  carrier_id: "CAR001",
  carrier_name: "Safexpress Logistics",
  bill_number: "",
  bill_date: new Date().toISOString().slice(0, 10),
  shipment_reference: "",
  lane: "DEL-BLR",
  billed_weight_kg: 100,
  rate_per_kg: 15,
  base_charge: 1500,
  fuel_surcharge: 120,
  gst_amount: 292,
  total_amount: 1912,
};

function tone(status: string) {
  if (status === "approved") return "good" as const;
  if (status === "awaiting_review" || status === "processing" || status === "pending") return "warn" as const;
  if (status === "disputed" || status === "rejected") return "danger" as const;
  return "neutral" as const;
}

export function BillsPage() {
  const { session } = useAuth();
  const { showToast } = useToast();
  const [bills, setBills] = useState<FreightBill[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<NewFreightBill>(emptyBill);
  const [selected, setSelected] = useState<FreightBill | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);

  async function refresh() {
    if (!session) return;
    setLoading(true);
    try {
      setBills(await api.bills(session));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh().catch(() => showToast("Could not load bills.", "error")); }, [session?.tenantId]);

  const visible = useMemo(() => bills.filter((bill) => {
    const matchesFilter = filter === "all" || bill.status === filter;
    const haystack = `${bill.id} ${bill.bill_number} ${bill.carrier_name} ${bill.lane}`.toLowerCase();
    return matchesFilter && haystack.includes(search.toLowerCase());
  }), [bills, filter, search]);

  async function openBill(bill: FreightBill) {
    if (!session) return;
    setSelected(bill);
    try {
      const [detail, events] = await Promise.all([api.bill(session, bill.id), api.audit(session, bill.id)]);
      setSelected(detail);
      setAudit(events);
    } catch {
      setAudit([]);
    }
  }

  function update<K extends keyof NewFreightBill>(key: K, value: NewFreightBill[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!session) return;
    try {
      const result = await api.createBill(session, draft);
      showToast(`${result.id} queued for validation.`, "success");
      setCreating(false);
      setDraft({ ...emptyBill, bill_number: "" });
      await refresh();
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Could not create bill.", "error");
    }
  }

  return (
    <div className="grid gap-6">
      <header className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div><p className="text-xs font-bold uppercase tracking-[0.2em] text-emerald-700 dark:text-[#d8ff5f]">Operations</p><h1 className="mt-2 text-3xl font-semibold tracking-[-0.03em]">Freight bills</h1><p className="mt-2 text-sm text-slate-500 dark:text-white/45">Search, ingest and inspect every bill moving through the audit workflow.</p></div>
        <div className="flex gap-2"><Button variant="secondary" onClick={refresh} icon={<RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />}>Refresh</Button><Button onClick={() => setCreating(true)} icon={<FilePlus2 className="h-4 w-4" />}>New freight bill</Button></div>
      </header>

      <Card className="overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-slate-200 p-4 dark:border-white/10 md:flex-row md:items-center">
          <div className="relative flex-1"><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><input value={search} onChange={(event) => setSearch(event.target.value)} className="h-11 w-full rounded-xl border border-slate-200 bg-slate-50 pl-10 pr-4 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/10 dark:border-white/10 dark:bg-white/5" placeholder="Search bill ID, carrier, number or lane" /></div>
          <div className="flex gap-2 overflow-x-auto">{["all", "pending", "processing", "awaiting_review", "approved", "disputed"].map((item) => <button key={item} onClick={() => setFilter(item)} className={`whitespace-nowrap rounded-xl px-3 py-2 text-xs font-medium transition ${filter === item ? "bg-[#173b33] text-white dark:bg-[#d8ff5f] dark:text-[#07110f]" : "bg-slate-100 text-slate-500 hover:text-slate-900 dark:bg-white/5 dark:text-white/50"}`}>{item.replaceAll("_", " ")}</button>)}</div>
          <Button variant="ghost" className="w-10 px-0"><SlidersHorizontal className="h-4 w-4" /></Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="bg-slate-50 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400 dark:bg-white/[0.025]"><tr><th className="px-5 py-3">Bill details</th><th className="px-5 py-3">Carrier</th><th className="px-5 py-3">Lane</th><th className="px-5 py-3">Amount</th><th className="px-5 py-3">Confidence</th><th className="px-5 py-3">Status</th><th className="w-12" /></tr></thead>
            <tbody>{visible.map((bill) => <tr key={bill.id} onClick={() => openBill(bill)} className="cursor-pointer border-t border-slate-100 transition hover:bg-emerald-50/40 dark:border-white/5 dark:hover:bg-white/[0.04]"><td className="px-5 py-4"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-slate-100 text-slate-500 dark:bg-white/10"><FileSearch className="h-4 w-4" /></span><div><p className="font-semibold">{bill.id}</p><p className="mt-0.5 text-xs text-slate-400">{bill.bill_number}</p></div></div></td><td className="px-5 py-4"><p className="font-medium">{bill.carrier_name}</p><p className="mt-0.5 text-xs text-slate-400">{bill.bill_date ?? "Date unavailable"}</p></td><td className="px-5 py-4 font-medium">{bill.lane}</td><td className="px-5 py-4 font-semibold">{formatCurrency(bill.total_amount)}</td><td className="px-5 py-4"><div className="flex items-center gap-2"><div className="h-1.5 w-14 overflow-hidden rounded-full bg-slate-100 dark:bg-white/10"><div className="h-full rounded-full bg-emerald-500" style={{width: `${(bill.confidence_score ?? 0) * 100}%`}} /></div><span>{formatPercent(bill.confidence_score)}</span></div></td><td className="px-5 py-4"><Badge tone={tone(bill.status)}>{bill.status.replaceAll("_", " ")}</Badge></td><td className="px-4"><ChevronRight className="h-4 w-4 text-slate-300" /></td></tr>)}</tbody>
          </table>
          {!visible.length ? <div className="grid place-items-center px-6 py-20 text-center"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-slate-100 text-slate-400 dark:bg-white/10"><Filter className="h-5 w-5" /></span><h3 className="mt-4 font-semibold">No bills match this view</h3><p className="mt-1 text-sm text-slate-400">Change the filter or ingest a new freight bill.</p></div> : null}
        </div>
        <div className="flex items-center justify-between border-t border-slate-200 px-5 py-3 text-xs text-slate-400 dark:border-white/10"><span>{visible.length} of {bills.length} bills</span><span className="flex items-center gap-1"><ArrowDownUp className="h-3.5 w-3.5" /> Newest first</span></div>
      </Card>

      {creating ? <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/55 backdrop-blur-sm" onMouseDown={() => setCreating(false)}><aside className="h-full w-full max-w-2xl overflow-y-auto bg-white p-6 shadow-2xl dark:bg-[#0b1714]" onMouseDown={(event) => event.stopPropagation()}><div className="flex items-start justify-between"><div><p className="text-xs font-bold uppercase tracking-[0.2em] text-emerald-700 dark:text-[#d8ff5f]">New intake</p><h2 className="mt-2 text-2xl font-semibold">Create freight bill</h2><p className="mt-1 text-sm text-slate-500">The bill is persisted first, then queued for agent validation.</p></div><button onClick={() => setCreating(false)} className="grid h-9 w-9 place-items-center rounded-xl bg-slate-100 dark:bg-white/10"><X className="h-4 w-4" /></button></div><form onSubmit={submit} className="mt-8 grid gap-5"><div className="grid gap-4 sm:grid-cols-2"><Input required label="Carrier name" value={draft.carrier_name} onChange={(e) => update("carrier_name", e.target.value)} /><Input label="Carrier ID" value={draft.carrier_id} onChange={(e) => update("carrier_id", e.target.value)} /><Input required label="Bill number" value={draft.bill_number} onChange={(e) => update("bill_number", e.target.value)} /><Input required label="Bill date" type="date" value={draft.bill_date} onChange={(e) => update("bill_date", e.target.value)} /><Input label="Shipment reference" value={draft.shipment_reference} onChange={(e) => update("shipment_reference", e.target.value)} /><Input required label="Lane" value={draft.lane} onChange={(e) => update("lane", e.target.value)} /><Input required label="Billed weight (kg)" type="number" min="1" value={draft.billed_weight_kg} onChange={(e) => update("billed_weight_kg", Number(e.target.value))} /><Input label="Rate per kg" type="number" min="0" step="0.01" value={draft.rate_per_kg} onChange={(e) => update("rate_per_kg", Number(e.target.value))} /></div><div className="rounded-2xl bg-slate-50 p-5 dark:bg-white/5"><h3 className="mb-4 text-sm font-semibold">Charge summary</h3><div className="grid gap-4 sm:grid-cols-2"><Input required label="Base charge" type="number" min="0" step="0.01" value={draft.base_charge} onChange={(e) => update("base_charge", Number(e.target.value))} /><Input required label="Fuel surcharge" type="number" min="0" step="0.01" value={draft.fuel_surcharge} onChange={(e) => update("fuel_surcharge", Number(e.target.value))} /><Input required label="GST amount" type="number" min="0" step="0.01" value={draft.gst_amount} onChange={(e) => update("gst_amount", Number(e.target.value))} /><Input required label="Total amount" type="number" min="0.01" step="0.01" value={draft.total_amount} onChange={(e) => update("total_amount", Number(e.target.value))} /></div></div><div className="flex items-center justify-between border-t border-slate-200 pt-5 dark:border-white/10"><p className="flex items-center gap-2 text-xs text-slate-400"><CheckCircle2 className="h-4 w-4 text-emerald-500" /> Duplicate protection enabled</p><div className="flex gap-2"><Button type="button" variant="secondary" onClick={() => setCreating(false)}>Cancel</Button><Button type="submit" icon={<FilePlus2 className="h-4 w-4" />}>Queue bill</Button></div></div></form></aside></div> : null}

      {selected ? <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/45 backdrop-blur-sm" onMouseDown={() => setSelected(null)}><aside className="h-full w-full max-w-lg overflow-y-auto bg-white p-6 shadow-2xl dark:bg-[#0b1714]" onMouseDown={(event) => event.stopPropagation()}><div className="flex items-start justify-between"><div><Badge tone={tone(selected.status)}>{selected.status.replaceAll("_", " ")}</Badge><h2 className="mt-3 text-2xl font-semibold">{selected.id}</h2><p className="text-sm text-slate-400">{selected.carrier_name} · {selected.bill_number}</p></div><button onClick={() => setSelected(null)} className="grid h-9 w-9 place-items-center rounded-xl bg-slate-100 dark:bg-white/10"><X className="h-4 w-4" /></button></div><div className="mt-7 grid grid-cols-2 gap-3">{[["Amount",formatCurrency(selected.total_amount)],["Confidence",formatPercent(selected.confidence_score)],["Lane",selected.lane],["Bill date",selected.bill_date ?? "--"]].map(([label,value]) => <div key={label} className="rounded-2xl bg-slate-50 p-4 dark:bg-white/5"><p className="text-[10px] uppercase tracking-wide text-slate-400">{label}</p><p className="mt-2 font-semibold">{value}</p></div>)}</div><div className="mt-6"><h3 className="text-sm font-semibold">Decision rationale</h3><p className="mt-2 rounded-2xl border border-slate-200 p-4 text-sm leading-6 text-slate-500 dark:border-white/10">{selected.decision_reason || "The agent has not produced a final rationale yet."}</p></div><div className="mt-6"><h3 className="text-sm font-semibold">Audit timeline</h3><div className="mt-4 space-y-0">{audit.map((event, index) => <div key={`${event.event}-${index}`} className="grid grid-cols-[20px_1fr] gap-3"><div className="flex flex-col items-center"><span className="mt-1 h-2.5 w-2.5 rounded-full bg-emerald-500" />{index < audit.length - 1 ? <span className="h-12 w-px bg-slate-200 dark:bg-white/10" /> : null}</div><div><p className="text-sm font-medium">{event.event.replaceAll("_", " ")}</p><p className="mt-1 text-xs text-slate-400">{new Date(event.created_at).toLocaleString()}</p></div></div>)}{!audit.length ? <p className="text-sm text-slate-400">Audit events will appear as processing advances.</p> : null}</div></div></aside></div> : null}
    </div>
  );
}
