import { ArrowRight, BarChart3, Check, CheckCircle2, CircleDollarSign, FileSearch, KeyRound, Menu, Play, ShieldCheck, Sparkles, Truck, X, Zap } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useAuth } from "../../context/AuthContext";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";

const proof = ["Contract-aware validation", "Human-in-the-loop controls", "Every decision fully traceable"];

export function AuthScreen({ onOpenDemo }: { onOpenDemo: () => void }) {
  const { login } = useAuth();
  const [showLogin, setShowLogin] = useState(false);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin");
  const [tenantId, setTenantId] = useState("default");

  function submit(event: FormEvent) {
    event.preventDefault();
    login({ username, password, tenantId });
  }

  return (
    <main className="min-h-screen overflow-hidden bg-[#07110f] text-white">
      <nav className="relative z-20 mx-auto flex max-w-7xl items-center justify-between px-6 py-6 lg:px-8">
        <a href="#top" className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#d8ff5f] text-[#07110f]"><Truck className="h-5 w-5" /></span>
          <span><strong className="block leading-none">FreightFlow</strong><small className="text-[10px] uppercase tracking-[0.2em] text-white/45">AI control tower</small></span>
        </a>
        <div className="hidden items-center gap-8 text-sm text-white/60 md:flex">
          <a href="#platform" className="transition hover:text-white">Platform</a>
          <a href="#workflow" className="transition hover:text-white">How it works</a>
          <a href="#security" className="transition hover:text-white">Controls</a>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowLogin(true)} className="hidden px-4 py-2 text-sm text-white/70 hover:text-white sm:block">Sign in</button>
          <Button onClick={onOpenDemo} className="bg-[#d8ff5f] text-[#07110f] shadow-none hover:bg-[#e5ff93] dark:bg-[#d8ff5f] dark:text-[#07110f]">Process demo data <Play className="h-4 w-4" /></Button>
          <Menu className="h-5 w-5 text-white/60 md:hidden" />
        </div>
      </nav>

      <section id="top" className="relative mx-auto grid max-w-7xl items-center gap-14 px-6 pb-24 pt-16 lg:grid-cols-[.9fr_1.1fr] lg:px-8 lg:pb-32 lg:pt-24">
        <div className="absolute -left-48 top-0 h-[500px] w-[500px] rounded-full bg-emerald-500/10 blur-[120px]" />
        <div className="relative z-10">
          <div className="inline-flex items-center gap-2 rounded-full border border-[#d8ff5f]/20 bg-[#d8ff5f]/10 px-3 py-1.5 text-xs font-semibold text-[#d8ff5f]"><Sparkles className="h-3.5 w-3.5" /> Built for modern finance teams</div>
          <h1 className="mt-7 text-5xl font-semibold leading-[1.02] tracking-[-0.05em] sm:text-6xl lg:text-[74px]">Every freight bill.<br /><span className="text-[#d8ff5f]">Under control.</span></h1>
          <p className="mt-6 max-w-xl text-lg leading-8 text-white/58">Audit carrier invoices against contracts, shipment evidence and bills of lading in minutes. Your team reviews only the exceptions that need judgment.</p>
          <div className="mt-9 flex flex-wrap gap-3">
            <Button onClick={onOpenDemo} className="h-12 bg-[#d8ff5f] px-6 text-[#07110f] shadow-[0_16px_50px_rgba(216,255,95,.12)] hover:bg-[#e5ff93] dark:bg-[#d8ff5f] dark:text-[#07110f]">Process demo data <Play className="h-4 w-4" /></Button>
            <button onClick={() => setShowLogin(true)} className="inline-flex h-12 items-center rounded-lg border border-white/15 px-6 text-sm font-medium text-white/80 transition hover:bg-white/10">Open live workspace</button>
          </div>
          <div className="mt-9 flex flex-wrap gap-x-6 gap-y-3">
            {proof.map((item) => <span key={item} className="flex items-center gap-2 text-xs text-white/45"><Check className="h-3.5 w-3.5 text-emerald-400" /> {item}</span>)}
          </div>
        </div>

        <div className="relative">
          <div className="absolute -inset-16 rounded-full bg-[#d8ff5f]/[0.05] blur-3xl" />
          <div className="relative overflow-hidden rounded-[28px] border border-white/10 bg-[#0d1b18] p-3 shadow-[0_40px_120px_rgba(0,0,0,.45)]">
            <div className="rounded-[22px] border border-white/[0.08] bg-[#f7f9f8] p-5 text-slate-900">
              <div className="flex items-center justify-between border-b border-slate-200 pb-4">
                <div><p className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-700">Live control tower</p><h2 className="mt-1 text-lg font-semibold">Operations overview</h2></div>
                <div className="flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1 text-[10px] font-semibold text-emerald-700"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Agent online</div>
              </div>
              <div className="mt-4 grid grid-cols-3 gap-3">
                {[['Bills audited','1,284','+18%'],['Value protected','₹14.8L','this month'],['Auto-cleared','82.4%','high confidence']].map(([label,value,note]) => <div key={label} className="rounded-xl border border-slate-200 bg-white p-3"><p className="text-[9px] uppercase tracking-wide text-slate-400">{label}</p><p className="mt-2 text-xl font-semibold">{value}</p><p className="mt-1 text-[9px] text-emerald-600">{note}</p></div>)}
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-[1.35fr_.65fr]">
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <div className="flex items-center justify-between"><div><p className="text-xs font-semibold">Audit throughput</p><p className="text-[9px] text-slate-400">Last 7 days</p></div><BarChart3 className="h-4 w-4 text-emerald-700" /></div>
                  <div className="mt-6 flex h-28 items-end gap-2">{[42,68,54,80,64,91,76,96,82,100].map((height, index) => <div key={index} className={`flex-1 rounded-t ${index === 9 ? 'bg-[#173b33]' : 'bg-emerald-100'}`} style={{height: `${height}%`}} />)}</div>
                </div>
                <div className="rounded-xl bg-[#102e27] p-4 text-white"><p className="text-[9px] uppercase tracking-wide text-white/45">Agent impact</p><p className="mt-3 text-3xl font-semibold text-[#d8ff5f]">8.2h</p><p className="text-[10px] text-white/50">saved per 100 bills</p><div className="mt-6 space-y-2 text-[9px]"><div className="flex justify-between"><span className="text-white/50">Rule checks</span><span>100%</span></div><div className="h-1.5 rounded-full bg-white/10"><div className="h-full w-full rounded-full bg-[#d8ff5f]" /></div><div className="flex justify-between"><span className="text-white/50">Evidence linked</span><span>94%</span></div><div className="h-1.5 rounded-full bg-white/10"><div className="h-full w-[94%] rounded-full bg-emerald-400" /></div></div></div>
              </div>
              <div className="mt-3 flex items-center justify-between rounded-xl border border-amber-200 bg-amber-50 p-3"><div className="flex items-center gap-3"><span className="grid h-8 w-8 place-items-center rounded-lg bg-amber-100 text-amber-700"><FileSearch className="h-4 w-4" /></span><div><p className="text-xs font-semibold">3 exceptions need review</p><p className="text-[9px] text-slate-500">Rate variance and missing BOL evidence</p></div></div><span className="rounded-lg bg-white px-3 py-1.5 text-[9px] font-semibold shadow-sm">Review queue</span></div>
            </div>
          </div>
          <div className="absolute -bottom-5 -left-7 hidden items-center gap-3 rounded-2xl border border-white/10 bg-[#12221e] p-3 shadow-2xl sm:flex"><span className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-400/15 text-emerald-300"><CheckCircle2 className="h-5 w-5" /></span><div><p className="text-xs font-semibold">Invoice auto-approved</p><p className="text-[10px] text-white/40">99% confidence · just now</p></div></div>
        </div>
      </section>

      <section id="platform" className="bg-[#f4f7f6] px-6 py-24 text-slate-950 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="max-w-2xl"><p className="text-xs font-bold uppercase tracking-[0.22em] text-emerald-700">One operating layer</p><h2 className="mt-4 text-4xl font-semibold tracking-[-0.04em] md:text-5xl">From invoice intake to accountable decision.</h2><p className="mt-4 text-slate-500">Purpose-built workflows give finance operators speed without giving up evidence, control or human judgment.</p></div>
          <div className="mt-12 grid gap-5 md:grid-cols-3">
            {[{icon:Zap,title:'Continuous validation',text:'Check totals, rates, weights, duplicate invoices and contract dates with deterministic rules.'},{icon:FileSearch,title:'Evidence graph',text:'Connect every decision to its carrier, contract, shipment and bill of lading context.'},{icon:ShieldCheck,title:'Controlled AI',text:'Use model reasoning only for ambiguity. Exact finance checks remain reproducible Python rules.'}].map(({icon:Icon,title,text}, index) => <article key={title} className={`rounded-3xl border p-7 ${index === 1 ? 'border-[#173b33] bg-[#173b33] text-white' : 'border-slate-200 bg-white'}`}><span className={`grid h-11 w-11 place-items-center rounded-xl ${index === 1 ? 'bg-[#d8ff5f] text-[#07110f]' : 'bg-emerald-50 text-emerald-800'}`}><Icon className="h-5 w-5" /></span><h3 className="mt-8 text-xl font-semibold">{title}</h3><p className={`mt-3 text-sm leading-6 ${index === 1 ? 'text-white/55' : 'text-slate-500'}`}>{text}</p></article>)}
          </div>
        </div>
      </section>

      <section id="workflow" className="bg-white px-6 py-24 text-slate-950 lg:px-8"><div className="mx-auto max-w-7xl"><div className="grid gap-12 lg:grid-cols-[.7fr_1.3fr]"><div><p className="text-xs font-bold uppercase tracking-[0.22em] text-emerald-700">Workflow</p><h2 className="mt-4 text-4xl font-semibold tracking-[-0.04em]">A calm queue, even on busy days.</h2><p className="mt-4 leading-7 text-slate-500">The worker fleet handles volume in the background. Reviewers enter only when confidence or policy demands it.</p></div><div className="grid gap-3">{[['01','Ingest','API validates, de-duplicates and queues the bill.'],['02','Investigate','The agent joins contract, shipment and delivery evidence.'],['03','Decide','Exact rules score the bill; AI resolves bounded ambiguity.'],['04','Review','Exceptions pause durably until an authorized human responds.']].map(([number,title,text]) => <div key={number} className="grid grid-cols-[52px_1fr] gap-4 rounded-2xl border border-slate-200 p-5"><span className="grid h-10 w-10 place-items-center rounded-xl bg-slate-100 text-xs font-bold text-emerald-800">{number}</span><div><h3 className="font-semibold">{title}</h3><p className="mt-1 text-sm text-slate-500">{text}</p></div></div>)}</div></div></div></section>

      <section id="security" className="border-t border-white/10 px-6 py-20 lg:px-8"><div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-8 md:flex-row md:items-center"><div><p className="text-sm font-semibold text-[#d8ff5f]">Ready to inspect the workflow?</p><h2 className="mt-3 max-w-2xl text-3xl font-semibold tracking-tight">Process a synthetic bill from API input through graph evidence to final output—entirely in your browser.</h2></div><Button onClick={onOpenDemo} className="h-12 bg-white px-6 text-[#07110f] shadow-none hover:bg-white/90 dark:bg-white dark:text-[#07110f]">Process demo data <Play className="h-4 w-4" /></Button></div></section>

      <footer className="border-t border-white/10 px-6 py-8 text-xs text-white/35 lg:px-8"><div className="mx-auto flex max-w-7xl flex-col justify-between gap-3 sm:flex-row"><span>© 2026 FreightFlow AI</span><span>Auditable automation for freight finance</span></div></footer>

      {showLogin ? <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm" onMouseDown={() => setShowLogin(false)}><aside className="h-full w-full max-w-md overflow-y-auto bg-white p-7 text-slate-950 shadow-2xl" onMouseDown={(event) => event.stopPropagation()}><div className="flex items-center justify-between"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#173b33] text-[#d8ff5f]"><Truck className="h-5 w-5" /></span><strong>FreightFlow</strong></div><button onClick={() => setShowLogin(false)} className="grid h-9 w-9 place-items-center rounded-lg bg-slate-100"><X className="h-4 w-4" /></button></div><div className="mt-16"><p className="text-xs font-bold uppercase tracking-[0.2em] text-emerald-700">Welcome back</p><h2 className="mt-3 text-3xl font-semibold tracking-tight">Enter your control tower</h2><p className="mt-3 text-sm leading-6 text-slate-500">Use the bootstrap workspace credentials for the local product environment.</p></div><form className="mt-9 grid gap-5" onSubmit={submit}><Input label="Workspace tenant" value={tenantId} onChange={(event) => setTenantId(event.target.value)} /><Input label="Username" value={username} onChange={(event) => setUsername(event.target.value)} /><Input label="Password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} /><Button className="mt-2 h-12 bg-[#173b33] hover:bg-[#245447] dark:bg-[#173b33] dark:text-white" icon={<KeyRound className="h-4 w-4" />} type="submit">Sign in securely</Button></form><div className="mt-8 rounded-2xl bg-slate-50 p-4 text-xs leading-5 text-slate-500"><strong className="block text-slate-800">Local demo access</strong>Tenant <code>default</code> · username <code>admin</code> · password <code>admin</code></div><div className="mt-8 grid grid-cols-3 gap-2 text-center text-[10px] text-slate-400"><div><CircleDollarSign className="mx-auto mb-2 h-4 w-4 text-emerald-700" />Finance-grade</div><div><ShieldCheck className="mx-auto mb-2 h-4 w-4 text-emerald-700" />Auditable</div><div><Zap className="mx-auto mb-2 h-4 w-4 text-emerald-700" />Real-time</div></div></aside></div> : null}
    </main>
  );
}
