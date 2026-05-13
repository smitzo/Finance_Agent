import { Save, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Badge } from "../components/ui/Badge";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { api } from "../lib/api";
import type { PartnerDraft, PartnerFirm } from "../types";

const emptyDraft: PartnerDraft = {
  name: "",
  registrationNumber: "",
  gstin: "",
  contactName: "",
  contactEmail: "",
  contactPhone: "",
};

export function PartnerPage() {
  const { session } = useAuth();
  const { showToast } = useToast();
  const [partners, setPartners] = useState<PartnerFirm[]>([]);
  const [draft, setDraft] = useState<PartnerDraft>(() => {
    const stored = localStorage.getItem("partner-draft");
    return stored ? JSON.parse(stored) : emptyDraft;
  });
  const [message, setMessage] = useState("Maintain CA firm or audit partner details.");

  useEffect(() => {
    if (!session) return;
    api.partners(session).then(setPartners).catch(() => setPartners([]));
  }, [session?.tenantId]);

  function update(field: keyof PartnerDraft, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  function saveDraft() {
    localStorage.setItem("partner-draft", JSON.stringify(draft));
    setMessage("Partner draft saved locally.");
    showToast("Partner draft saved.", "success");
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_420px]">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <ShieldCheck className="h-5 w-5 text-teal-600 dark:text-teal-300" />
            <div>
              <h1 className="font-semibold">CA partner setup</h1>
              <p className="mt-1 text-sm text-slate-500 dark:text-zinc-400">{message}</p>
            </div>
          </div>
        </CardHeader>
        <CardBody className="grid gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Input label="Firm name" value={draft.name} onChange={(event) => update("name", event.target.value)} />
            <Input label="Registration number" value={draft.registrationNumber} onChange={(event) => update("registrationNumber", event.target.value)} />
            <Input label="GSTIN" value={draft.gstin} onChange={(event) => update("gstin", event.target.value)} />
            <Input label="Contact name" value={draft.contactName} onChange={(event) => update("contactName", event.target.value)} />
            <Input label="Contact email" type="email" value={draft.contactEmail} onChange={(event) => update("contactEmail", event.target.value)} />
            <Input label="Contact phone" value={draft.contactPhone} onChange={(event) => update("contactPhone", event.target.value)} />
          </div>
          <div className="flex justify-end">
            <Button icon={<Save className="h-4 w-4" />} onClick={saveDraft}>Save partner draft</Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="font-semibold">Linked partner firms</h2>
          <p className="mt-1 text-sm text-slate-500 dark:text-zinc-400">Loaded from the tenant backend.</p>
        </CardHeader>
        <CardBody className="grid gap-3">
          {partners.map((partner) => (
            <div key={partner.id} className="rounded-xl bg-slate-50 p-4 dark:bg-white/5">
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-medium">{partner.name}</h3>
                <Badge tone="good">{partner.status}</Badge>
              </div>
              <p className="mt-2 text-sm text-slate-500 dark:text-zinc-400">{partner.contact_name} · {partner.contact_email}</p>
              <p className="mt-1 text-xs text-slate-500 dark:text-zinc-500">{partner.registration_number ?? "No registration number"}</p>
            </div>
          ))}
          {!partners.length ? (
            <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500 dark:bg-white/5 dark:text-zinc-400">
              No partner firms found yet. Load demo data or save a local draft.
            </p>
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}
