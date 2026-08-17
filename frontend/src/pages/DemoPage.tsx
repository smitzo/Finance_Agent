import {
  ArrowLeft,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Code2,
  Database,
  FileInput,
  GitBranch,
  Layers3,
  LoaderCircle,
  Network,
  Play,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  Truck,
  UserRoundCheck,
  XCircle,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import {
  demoBatchBills,
  demoScenarios,
  processDemoBill,
  scenarioById,
  type DemoBillInput,
  type DemoGraphNode,
  type DemoRun,
  type DemoScenario,
} from "../demo/demoEngine";

type DemoPageProps = {
  standalone?: boolean;
  onBack?: () => void;
};

type BatchResult = {
  scenario: DemoScenario;
  run: DemoRun;
};

const stageIcons = [FileInput, Database, Network, ShieldCheck, Bot, GitBranch, CheckCircle2];

const nodeColors: Record<DemoGraphNode["kind"], string> = {
  bill: "#d8ff5f",
  carrier: "#34d399",
  contract: "#60a5fa",
  lane: "#fbbf24",
  shipment: "#a78bfa",
  bol: "#22d3ee",
  missing: "#fb7185",
};

const decisionStyles: Record<DemoRun["decision"], string> = {
  auto_approve: "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-400/20 dark:bg-emerald-400/[0.08] dark:text-emerald-100",
  flag: "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-400/20 dark:bg-amber-400/[0.08] dark:text-amber-100",
  dispute: "border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-400/20 dark:bg-rose-400/[0.08] dark:text-rose-100",
  reject: "border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-400/20 dark:bg-rose-400/[0.08] dark:text-rose-100",
};

function delay(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function JsonBlock({ value, tone = "dark" }: { value: unknown; tone?: "dark" | "light" }) {
  return (
    <pre className={`max-h-72 overflow-auto rounded-xl p-4 text-[11px] leading-5 ${tone === "dark" ? "bg-[#07110f] text-emerald-100" : "bg-slate-50 text-slate-700 dark:bg-black/20 dark:text-zinc-300"}`}>
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function EvidenceGraph({ run, visible }: { run: DemoRun; visible: boolean }) {
  const positions = new Map(run.graphNodes.map((node) => [node.id, node]));
  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-[#07110f]">
      <div className="absolute left-4 top-4 z-10 flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-emerald-200">
        <Network className="h-3.5 w-3.5" /> Tenant evidence subgraph
      </div>
      <svg viewBox="0 0 760 410" className="min-h-[360px] w-full" role="img" aria-label="Freight bill evidence graph">
        <defs>
          <marker id="demo-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#5f7f76" />
          </marker>
        </defs>
        {run.graphEdges.map((edge) => {
          const from = positions.get(edge.from);
          const to = positions.get(edge.to);
          if (!from || !to) return null;
          const midX = (from.x + to.x) / 2;
          const midY = (from.y + to.y) / 2;
          return (
            <g key={`${edge.from}-${edge.to}`} className={`transition-opacity duration-700 ${visible ? "opacity-100" : "opacity-10"}`}>
              <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="#42655b" strokeWidth="1.6" markerEnd="url(#demo-arrow)" />
              <rect x={midX - 42} y={midY - 9} width="84" height="18" rx="9" fill="#0d1b18" stroke="#28473f" />
              <text x={midX} y={midY + 3} textAnchor="middle" fill="#86a79e" fontSize="8">{edge.label}</text>
            </g>
          );
        })}
        {run.graphNodes.map((node) => (
          <g key={node.id} className={`transition-all duration-700 ${visible ? "opacity-100" : "opacity-25"}`} transform={`translate(${node.x - 62} ${node.y - 27})`}>
            <rect width="124" height="54" rx="13" fill="#102e27" stroke={nodeColors[node.kind]} strokeWidth={node.kind === "bill" ? 2.5 : 1.5} strokeDasharray={node.kind === "missing" ? "5 4" : undefined} />
            <circle cx="13" cy="13" r="4" fill={nodeColors[node.kind]} />
            <text x="62" y="24" textAnchor="middle" fill="#f6fffb" fontSize="10" fontWeight="600">{node.label.length > 20 ? `${node.label.slice(0, 19)}…` : node.label}</text>
            <text x="62" y="39" textAnchor="middle" fill="#87a59d" fontSize="8">{node.meta.length > 27 ? `${node.meta.slice(0, 26)}…` : node.meta}</text>
          </g>
        ))}
      </svg>
      <div className="absolute bottom-4 left-4 right-4 flex flex-wrap gap-3 text-[9px] text-white/45">
        {Object.entries(nodeColors).map(([kind, color]) => <span key={kind} className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} /> {kind}</span>)}
      </div>
    </div>
  );
}

function validateBatch(value: unknown): DemoBillInput[] {
  if (!Array.isArray(value)) throw new Error("Input must be a JSON array of freight bills.");
  if (value.length < 1) throw new Error("Add at least one freight bill.");
  if (value.length > 50) throw new Error("The browser demonstration is limited to 50 bills per run.");
  const bills = value as DemoBillInput[];
  const required: Array<keyof DemoBillInput> = ["id", "bill_number", "carrier_name", "lane"];
  bills.forEach((bill, index) => {
    if (!bill || typeof bill !== "object") throw new Error(`Item ${index + 1} must be a freight bill object.`);
    const missing = required.filter((field) => !bill[field]);
    if (missing.length) throw new Error(`Item ${index + 1} is missing: ${missing.join(", ")}.`);
  });
  const ids = bills.map((bill) => bill.id);
  if (new Set(ids).size !== ids.length) throw new Error("Every freight bill ID must be unique within the batch.");
  return bills;
}

export function DemoPage({ standalone = false, onBack }: DemoPageProps) {
  const [input, setInput] = useState(() => JSON.stringify(demoBatchBills, null, 2));
  const [results, setResults] = useState<BatchResult[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [visibleSteps, setVisibleSteps] = useState(0);
  const [processing, setProcessing] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);
  const runToken = useRef(0);

  const selected = results[selectedIndex] ?? null;
  const run = selected?.run ?? null;
  const activeStage = run && visibleSteps ? run.stages[Math.min(visibleSteps - 1, run.stages.length - 1)] : null;
  const finished = Boolean(results.length && run && visibleSteps === run.stages.length && !processing);
  const inputCount = useMemo(() => {
    try {
      const parsed = JSON.parse(input);
      return Array.isArray(parsed) ? parsed.length : 0;
    } catch {
      return 0;
    }
  }, [input]);
  const summary = useMemo(() => results.reduce((counts, item) => {
    counts[item.run.decision] += 1;
    return counts;
  }, { auto_approve: 0, flag: 0, dispute: 0, reject: 0 }), [results]);

  function resetDemo() {
    runToken.current += 1;
    setInput(JSON.stringify(demoBatchBills, null, 2));
    setResults([]);
    setSelectedIndex(0);
    setVisibleSteps(0);
    setProcessing(false);
    setInputError(null);
  }

  async function process() {
    let bills: DemoBillInput[];
    try {
      bills = validateBatch(JSON.parse(input));
    } catch (error) {
      setInputError(error instanceof Error ? error.message : "Input must be valid JSON.");
      return;
    }

    const nextResults = bills.map((bill, index) => {
      const fallbackScenario = demoScenarios[index % demoScenarios.length].id;
      const scenario = scenarioById(bill.demo_scenario ?? fallbackScenario);
      return { scenario, run: processDemoBill(bill, scenario) };
    });
    const token = runToken.current + 1;
    runToken.current = token;
    setInputError(null);
    setResults(nextResults);
    setSelectedIndex(0);
    setVisibleSteps(0);
    setProcessing(true);
    for (let index = 1; index <= nextResults[0].run.stages.length; index += 1) {
      await delay(index === 1 ? 250 : 520);
      if (runToken.current !== token) return;
      setVisibleSteps(index);
    }
    if (runToken.current === token) setProcessing(false);
  }

  return (
    <main className={`${standalone ? "min-h-screen bg-[#f4f7f6] text-slate-950 dark:bg-[#07100e] dark:text-white" : ""}`}>
      {standalone ? (
        <header className="border-b border-slate-200 bg-white/90 px-5 py-4 backdrop-blur-xl dark:border-white/10 dark:bg-[#07100e]/90">
          <div className="mx-auto flex max-w-[1500px] items-center justify-between">
            <button onClick={onBack} className="flex items-center gap-3 text-left">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#173b33] text-[#d8ff5f]"><Truck className="h-5 w-5" /></span>
              <span><strong className="block">FreightFlow</strong><small className="text-slate-400">Interactive product demo</small></span>
            </button>
            <Button variant="secondary" onClick={onBack}><ArrowLeft className="h-4 w-4" /> Back to product</Button>
          </div>
        </header>
      ) : null}

      <div className={`${standalone ? "mx-auto max-w-[1500px] p-4 md:p-7" : ""} grid gap-6`}>
        <section className="relative overflow-hidden rounded-[28px] bg-[#102e27] p-6 text-white shadow-[0_24px_70px_rgba(16,46,39,.18)] md:p-8">
          <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-[#d8ff5f]/10 blur-3xl" />
          <div className="relative grid gap-7 lg:grid-cols-[1fr_auto] lg:items-end">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold text-[#d8ff5f]"><Sparkles className="h-4 w-4" /> Frontend-only batch demonstration</div>
              <h1 className="mt-4 max-w-4xl text-3xl font-semibold tracking-[-0.04em] md:text-5xl">Process ten freight bills, then inspect every decision.</h1>
              <p className="mt-4 max-w-3xl text-sm leading-6 text-white/55">This browser-local portfolio runs clean, ambiguous, duplicate, weight, total, and master-data cases together. Select any result to trace its simulated API, GraphDB, rule, model, and final output.</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/[0.06] p-4 text-xs leading-5 text-white/55 lg:max-w-xs">
              <strong className="flex items-center gap-2 text-white"><CircleDot className="h-4 w-4 text-[#d8ff5f]" /> Demonstration boundary</strong>
              <p className="mt-2">No processing request leaves this browser. The real backend uses FastAPI, Celery, PostgreSQL checkpoints, Neo4j, and an optional LLM provider.</p>
            </div>
          </div>
        </section>

        <section>
          <div className="mb-3 flex items-end justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-[0.18em] text-emerald-700 dark:text-emerald-300">Portfolio coverage</p><h2 className="mt-1 text-xl font-semibold">Six control paths across ten bills</h2></div><span className="text-xs text-slate-400">Safe, deterministic, browser-local</span></div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
            {demoScenarios.map((item) => (
              <div key={item.id} className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/[0.04]">
                <p className="text-[9px] font-bold uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-300">{item.eyebrow}</p>
                <h3 className="mt-2 text-sm font-semibold">{item.name}</h3>
                <p className="mt-2 text-[11px] leading-5 text-slate-500">{item.description}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[470px_1fr]">
          <Card className="h-fit overflow-hidden xl:sticky xl:top-20">
            <CardHeader className="flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-emerald-700 dark:text-emerald-300">Step 01</p><h2 className="mt-1 font-semibold">Freight bill batch input</h2></div><div className="flex items-center gap-2"><span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300">{inputCount} bills</span><Code2 className="h-5 w-5 text-slate-400" /></div></CardHeader>
            <CardBody>
              <textarea value={input} onChange={(event) => setInput(event.target.value)} spellCheck={false} className="h-[600px] w-full resize-none rounded-2xl border border-slate-200 bg-[#07110f] p-4 font-mono text-[11px] leading-5 text-emerald-100 outline-none focus:border-emerald-500 dark:border-white/10" />
              {inputError ? <p className="mt-3 flex items-center gap-2 text-xs text-rose-600"><XCircle className="h-4 w-4" /> {inputError}</p> : null}
              <div className="mt-4 grid grid-cols-[1fr_auto] gap-2">
                <Button onClick={process} disabled={processing} className="h-12 bg-[#173b33] dark:bg-[#d8ff5f]" icon={processing ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}>
                  {processing ? `Processing ${results.length} demo bills` : "Process demo data"}
                </Button>
                <Button variant="secondary" onClick={resetDemo} aria-label="Reset demo"><RotateCcw className="h-4 w-4" /></Button>
              </div>
              <p className="mt-3 text-[11px] leading-5 text-slate-400">Edit the array or add bills up to the 50-item browser-demo limit. Use <code>demo_scenario</code> to choose the synthetic evidence path.</p>
            </CardBody>
          </Card>

          <div className="grid min-w-0 gap-6">
            <Card>
              <CardHeader className="flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-emerald-700 dark:text-emerald-300">Live batch execution</p><h2 className="mt-1 font-semibold">Processing timeline</h2></div>{results.length ? <span className="flex items-center gap-2 text-xs text-slate-400"><Layers3 className="h-4 w-4" /> {results.length} parallel bill traces</span> : null}</CardHeader>
              <CardBody>
                <div className="grid gap-2 lg:grid-cols-7">
                  {(run?.stages ?? ["Validate", "Queue", "Graph", "Rules", "Model", "Decide", "Persist"].map((label, index) => ({ id: String(index), label, service: "Waiting", detail: "", skipped: false }))).map((stage, index) => {
                    const Icon = stageIcons[index];
                    const complete = visibleSteps > index;
                    const active = processing && visibleSteps === index;
                    return <div key={stage.id} className={`relative rounded-2xl border p-3 transition-all ${complete ? stage.skipped ? "border-slate-200 bg-slate-50 dark:border-white/10 dark:bg-white/[0.03]" : "border-emerald-200 bg-emerald-50 dark:border-emerald-400/20 dark:bg-emerald-400/[0.06]" : active ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white opacity-55 dark:border-white/10 dark:bg-white/[0.02]"}`}>
                      <span className={`grid h-8 w-8 place-items-center rounded-xl ${complete && !stage.skipped ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-500 dark:bg-white/10 dark:text-zinc-300"}`}>{complete && !stage.skipped ? <Check className="h-4 w-4" /> : <Icon className={`h-4 w-4 ${active ? "animate-pulse" : ""}`} />}</span>
                      <p className="mt-3 text-[11px] font-semibold leading-4">{stage.label}</p>
                      <p className="mt-1 text-[9px] leading-4 text-slate-400">{stage.service}</p>
                      {index < 6 ? <ChevronRight className="absolute -right-3 top-6 z-10 hidden h-4 w-4 text-slate-300 lg:block" /> : null}
                    </div>;
                  })}
                </div>
              </CardBody>
            </Card>

            {results.length && visibleSteps >= 6 ? (
              <section className="grid gap-3 sm:grid-cols-5">
                {[
                  ["Processed", results.length, "text-slate-950 dark:text-white"],
                  ["Approved", summary.auto_approve, "text-emerald-700 dark:text-emerald-300"],
                  ["Review", summary.flag, "text-amber-700 dark:text-amber-300"],
                  ["Disputed", summary.dispute, "text-rose-700 dark:text-rose-300"],
                  ["Rejected", summary.reject, "text-rose-900 dark:text-rose-200"],
                ].map(([label, value, tone]) => <div key={String(label)} className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/[0.04]"><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</p><p className={`mt-2 text-3xl font-semibold ${tone}`}>{value}</p></div>)}
              </section>
            ) : null}

            {results.length && visibleSteps >= 6 ? (
              <Card>
                <CardHeader className="flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-300">Batch outcomes</p><h3 className="mt-1 font-semibold">Select a bill to inspect its complete trace</h3></div><span className="text-xs text-slate-400">{results.length} results</span></CardHeader>
                <CardBody className="overflow-x-auto p-0">
                  <table className="w-full min-w-[780px] text-left text-xs">
                    <thead className="border-b border-slate-200 bg-slate-50 text-[10px] uppercase tracking-[0.12em] text-slate-400 dark:border-white/10 dark:bg-white/[0.03]"><tr><th className="px-5 py-3">Bill</th><th className="px-4 py-3">Scenario</th><th className="px-4 py-3">Lane</th><th className="px-4 py-3">Decision</th><th className="px-4 py-3">Confidence</th><th className="px-5 py-3">Primary result</th></tr></thead>
                    <tbody>{results.map((item, index) => {
                      const primary = item.run.findings.find((finding) => finding.severity === "error") ?? item.run.findings[0];
                      return <tr key={item.run.bill.id} onClick={() => setSelectedIndex(index)} className={`cursor-pointer border-b border-slate-100 transition last:border-0 dark:border-white/5 ${selectedIndex === index ? "bg-emerald-50 dark:bg-emerald-400/[0.06]" : "hover:bg-slate-50 dark:hover:bg-white/[0.03]"}`}><td className="px-5 py-4 font-semibold">{item.run.bill.id}</td><td className="px-4 py-4">{item.scenario.name}</td><td className="px-4 py-4 text-slate-500">{item.run.bill.lane}</td><td className="px-4 py-4"><span className={`rounded-full px-2.5 py-1 font-semibold capitalize ${item.run.decision === "auto_approve" ? "bg-emerald-100 text-emerald-700" : item.run.decision === "flag" ? "bg-amber-100 text-amber-700" : "bg-rose-100 text-rose-700"}`}>{item.run.decision.replace("_", " ")}</span></td><td className="px-4 py-4 font-semibold">{Math.round(item.run.confidence * 100)}%</td><td className="max-w-xs px-5 py-4 text-slate-500">{primary?.message}</td></tr>;
                    })}</tbody>
                  </table>
                </CardBody>
              </Card>
            ) : null}

            {run ? <div className="flex flex-col justify-between gap-2 rounded-2xl border border-slate-200 bg-white px-5 py-4 dark:border-white/10 dark:bg-white/[0.04] sm:flex-row sm:items-center"><div><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-300">Selected bill trace</p><h2 className="mt-1 font-semibold">{run.bill.id} · {selected?.scenario.name}</h2></div><p className="text-xs text-slate-400">Result {selectedIndex + 1} of {results.length}</p></div> : null}

            {run ? <EvidenceGraph run={run} visible={visibleSteps >= 3} /> : <div className="grid min-h-[360px] place-items-center rounded-2xl border border-dashed border-slate-300 bg-white text-center dark:border-white/15 dark:bg-white/[0.02]"><div><Network className="mx-auto h-9 w-9 text-slate-300" /><p className="mt-3 font-semibold">Batch evidence graphs will appear here</p><p className="mt-1 text-xs text-slate-400">Process the ten-bill portfolio, then inspect each result.</p></div></div>}

            {run && selected && visibleSteps >= 3 ? <div className="grid gap-6 lg:grid-cols-2"><Card><CardHeader className="flex items-center gap-3"><TerminalSquare className="h-5 w-5 text-blue-600" /><div><p className="text-xs font-bold uppercase tracking-[0.14em] text-blue-600">GraphDB call</p><h3 className="font-semibold">Cypher request</h3></div></CardHeader><CardBody><pre className="overflow-auto whitespace-pre-wrap rounded-xl bg-[#07110f] p-4 text-[10px] leading-5 text-cyan-100">{run.graphQuery}</pre></CardBody></Card><Card><CardHeader className="flex items-center gap-3"><Database className="h-5 w-5 text-violet-600" /><div><p className="text-xs font-bold uppercase tracking-[0.14em] text-violet-600">GraphDB response</p><h3 className="font-semibold">Connected evidence</h3></div></CardHeader><CardBody><JsonBlock tone="light" value={{ carrier: selected.scenario.reference.carrier, contracts: selected.scenario.reference.contracts, shipment: selected.scenario.reference.shipment, bols: selected.scenario.reference.bols, duplicates: selected.scenario.reference.duplicate_bill_ids }} /></CardBody></Card></div> : null}

            {run && visibleSteps >= 4 ? <Card><CardHeader className="flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-300">Deterministic controls</p><h3 className="mt-1 font-semibold">Financial findings</h3></div><span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-500 dark:bg-white/10">{run.findings.length} checks</span></CardHeader><CardBody className="grid gap-2 md:grid-cols-2">{run.findings.map((item) => <div key={item.code} className={`flex gap-3 rounded-xl border p-3 ${item.severity === "error" ? "border-rose-200 bg-rose-50 dark:border-rose-400/20 dark:bg-rose-400/[0.06]" : item.severity === "warn" ? "border-amber-200 bg-amber-50 dark:border-amber-400/20 dark:bg-amber-400/[0.06]" : "border-emerald-100 bg-emerald-50/60 dark:border-emerald-400/15 dark:bg-emerald-400/[0.04]"}`}><span className="mt-0.5">{item.severity === "error" ? <XCircle className="h-4 w-4 text-rose-600" /> : <CheckCircle2 className="h-4 w-4 text-emerald-600" />}</span><div><p className="text-[10px] font-bold tracking-wide">{item.code}</p><p className="mt-1 text-xs leading-5 text-slate-600 dark:text-zinc-300">{item.message}</p></div></div>)}</CardBody></Card> : null}

            {run && visibleSteps >= 5 ? <Card className={run.modelExchange ? "border-blue-200 dark:border-blue-400/20" : ""}><CardHeader className="flex items-center gap-3"><Bot className="h-5 w-5 text-blue-600" /><div><p className="text-xs font-bold uppercase tracking-[0.14em] text-blue-600">Bounded model step</p><h3 className="font-semibold">{run.modelExchange ? "Contract choice is constrained by graph evidence" : "No model call needed"}</h3></div></CardHeader><CardBody>{run.modelExchange ? <div className="grid gap-4 lg:grid-cols-2"><div><p className="mb-2 text-xs font-semibold text-slate-500">Model input</p><JsonBlock value={run.modelExchange.prompt} /></div><div><p className="mb-2 text-xs font-semibold text-slate-500">Model output</p><JsonBlock value={run.modelExchange.response} /></div></div> : <div className="flex items-start gap-3 rounded-xl bg-slate-50 p-4 dark:bg-white/[0.04]"><ShieldCheck className="mt-0.5 h-5 w-5 text-emerald-600" /><p className="text-sm leading-6 text-slate-600 dark:text-zinc-300">The policy guard skipped model reasoning because exact evidence was sufficient. This saves cost and prevents a model from overriding financial controls.</p></div>}</CardBody></Card> : null}

            {run && visibleSteps >= 6 ? <section className={`rounded-2xl border p-5 ${decisionStyles[run.decision]}`}><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center"><div><p className="text-[10px] font-bold uppercase tracking-[0.16em] opacity-60">Decision node</p><h2 className="mt-2 text-2xl font-semibold capitalize">{run.decision.replace("_", " ")}</h2><p className="mt-2 max-w-2xl text-sm leading-6 opacity-70">{run.explanation}</p></div><div className="shrink-0 text-left sm:text-right"><p className="text-4xl font-semibold">{Math.round(run.confidence * 100)}%</p><p className="text-xs opacity-60">explainable confidence</p></div></div>{run.decision === "flag" ? <div className="mt-4 flex items-center gap-2 border-t border-current/10 pt-4 text-xs"><UserRoundCheck className="h-4 w-4" /> Durable checkpoint → human review queue</div> : null}</section> : null}

            {run && visibleSteps >= 7 ? <Card className="overflow-hidden border-0 bg-[#102e27] text-white"><CardHeader className="flex items-center justify-between border-white/10"><div><p className="text-xs font-bold uppercase tracking-[0.14em] text-[#d8ff5f]">Final persisted output</p><h3 className="mt-1 font-semibold">API response and audit snapshot</h3></div><CheckCircle2 className="h-5 w-5 text-[#d8ff5f]" /></CardHeader><CardBody><JsonBlock value={run.finalOutput} /></CardBody></Card> : null}

            {activeStage ? <Card><CardHeader className="flex items-center gap-3"><TerminalSquare className="h-5 w-5 text-slate-500" /><div><p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Selected bill service exchange</p><h3 className="font-semibold">{activeStage.service}</h3></div></CardHeader><CardBody className="grid gap-4 lg:grid-cols-2"><div><p className="mb-2 text-xs font-semibold text-slate-500">Request</p><JsonBlock value={activeStage.request ?? { internal: true }} /></div><div><p className="mb-2 text-xs font-semibold text-slate-500">Response</p><JsonBlock value={activeStage.response} /></div></CardBody></Card> : null}

            {finished ? <div className="flex flex-col items-center justify-between gap-4 rounded-2xl border border-emerald-200 bg-white p-5 text-center dark:border-emerald-400/20 dark:bg-white/[0.04] sm:flex-row sm:text-left"><div><p className="font-semibold">Demonstration complete</p><p className="mt-1 text-xs text-slate-500">All {results.length} bills were processed. Select rows above to compare their evidence and decisions.</p></div><Button variant="secondary" onClick={resetDemo}><RotateCcw className="h-4 w-4" /> Run another batch</Button></div> : null}
          </div>
        </section>
      </div>
    </main>
  );
}
