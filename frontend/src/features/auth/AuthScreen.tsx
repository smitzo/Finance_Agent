import { KeyRound, Sparkles, UserPlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useAuth } from "../../context/AuthContext";
import { Button } from "../../components/ui/Button";
import { Card, CardBody } from "../../components/ui/Card";
import { Input } from "../../components/ui/Input";
import type { AuthMode } from "../../types";

export function AuthScreen() {
  const { login } = useAuth();
  const [mode, setMode] = useState<AuthMode>("login");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin");
  const [tenantId, setTenantId] = useState("default");

  function submit(event: FormEvent) {
    event.preventDefault();
    login({ username, password, tenantId });
  }

  return (
    <main className="relative min-h-screen overflow-hidden bg-slate-50 text-slate-950 dark:bg-zinc-950 dark:text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_15%,rgba(20,184,166,0.18),transparent_32%),radial-gradient(circle_at_80%_10%,rgba(59,130,246,0.14),transparent_30%)]" />
      <div className="relative mx-auto grid min-h-screen max-w-6xl items-center gap-10 px-6 py-10 lg:grid-cols-[1.05fr_0.95fr]">
        <section>
          <div className="inline-flex items-center gap-2 rounded-full border border-teal-500/20 bg-teal-500/10 px-3 py-1 text-sm font-medium text-teal-700 dark:text-teal-200">
            <Sparkles className="h-4 w-4" />
            AI-native freight validation OS
          </div>
          <h1 className="mt-6 max-w-2xl text-5xl font-semibold tracking-tight md:text-6xl">
            Freight audits that feel less like spreadsheets and more like radar.
          </h1>
          <p className="mt-5 max-w-xl text-lg leading-8 text-slate-600 dark:text-zinc-300">
            Validate carrier bills, read graph anomalies, review exceptions, and manage tenant operations from one calm command center.
          </p>
        </section>

        <Card className="shadow-glow">
          <CardBody className="p-6">
            <div className="grid grid-cols-2 gap-2 rounded-xl bg-slate-100 p-1 dark:bg-white/10">
              <button
                className={`rounded-lg px-3 py-2 text-sm font-medium transition ${mode === "login" ? "bg-white shadow-sm dark:bg-zinc-900" : "text-slate-500 dark:text-zinc-400"}`}
                onClick={() => setMode("login")}
              >
                Login
              </button>
              <button
                className={`rounded-lg px-3 py-2 text-sm font-medium transition ${mode === "signup" ? "bg-white shadow-sm dark:bg-zinc-900" : "text-slate-500 dark:text-zinc-400"}`}
                onClick={() => setMode("signup")}
              >
                Signup
              </button>
            </div>

            <form className="mt-6 grid gap-4" onSubmit={submit}>
              <Input label="Tenant" value={tenantId} onChange={(event) => setTenantId(event.target.value)} />
              <Input label="Username" value={username} onChange={(event) => setUsername(event.target.value)} />
              <Input label="Password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
              {mode === "signup" ? (
                <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-400/10 dark:text-amber-100">
                  Signup creates a local session for now. Use admin/admin for full backend access until DB users are enabled.
                </p>
              ) : null}
              <Button icon={mode === "login" ? <KeyRound className="h-4 w-4" /> : <UserPlus className="h-4 w-4" />} type="submit">
                {mode === "login" ? "Enter dashboard" : "Create workspace"}
              </Button>
            </form>
          </CardBody>
        </Card>
      </div>
    </main>
  );
}
