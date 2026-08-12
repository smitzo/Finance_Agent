import { Save } from "lucide-react";
import { useEffect, useState } from "react";
import { PageTitle } from "../components/common/PageTitle";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Input, Select } from "../components/ui/Input";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { api } from "../lib/api";
import type { CompanyDraft, CompanyProfile } from "../types";

const emptyDraft: CompanyDraft = {
  legalName: "",
  displayName: "",
  gstin: "",
  billingEmail: "",
  timezone: "Asia/Kolkata",
};

export function CompanyPage() {
  const { session } = useAuth();
  const { showToast } = useToast();
  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [draft, setDraft] = useState<CompanyDraft>(() => {
    const stored = localStorage.getItem("company-draft");
    return stored ? JSON.parse(stored) : emptyDraft;
  });
  const [message, setMessage] = useState("Create or review the tenant company profile.");

  useEffect(() => {
    if (!session) return;
    api.company(session).then(setProfile).catch(() => setProfile(null));
  }, [session?.tenantId]);

  function update(field: keyof CompanyDraft, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  async function saveDraft() {
    if (!session) return;
    try {
      const saved = await api.saveCompany(session, draft);
      setProfile(saved);
      localStorage.setItem("company-draft", JSON.stringify(draft));
      setMessage("Company profile saved to the tenant workspace.");
      showToast("Company profile saved.", "success");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Company could not be saved.", "error");
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
      <Card>
        <CardHeader>
          <PageTitle eyebrow="Company" title="Company setup" description={message} />
        </CardHeader>
        <CardBody className="grid gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Input label="Legal name" value={draft.legalName} onChange={(event) => update("legalName", event.target.value)} />
            <Input label="Display name" value={draft.displayName} onChange={(event) => update("displayName", event.target.value)} />
            <Input label="GSTIN" value={draft.gstin} onChange={(event) => update("gstin", event.target.value)} />
            <Input label="Billing email" type="email" value={draft.billingEmail} onChange={(event) => update("billingEmail", event.target.value)} />
            <Select label="Timezone" value={draft.timezone} onChange={(event) => update("timezone", event.target.value)}>
              <option>Asia/Kolkata</option>
              <option>UTC</option>
              <option>Europe/London</option>
            </Select>
          </div>
          <div className="flex justify-end">
            <Button icon={<Save className="h-4 w-4" />} onClick={saveDraft}>Save company profile</Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="font-semibold">Active backend profile</h2>
          <p className="mt-1 text-sm text-slate-500 dark:text-zinc-400">Loaded from the tenant API.</p>
        </CardHeader>
        <CardBody className="grid gap-3 text-sm">
          {profile ? (
            <>
              <p><span className="text-slate-500 dark:text-zinc-400">Company:</span> {profile.display_name}</p>
              <p><span className="text-slate-500 dark:text-zinc-400">Legal:</span> {profile.legal_name}</p>
              <p><span className="text-slate-500 dark:text-zinc-400">Billing:</span> {profile.billing_email}</p>
              <p><span className="text-slate-500 dark:text-zinc-400">CA firm:</span> {profile.ca_partner_firm?.name ?? "Not linked"}</p>
            </>
          ) : (
            <p className="text-slate-500 dark:text-zinc-400">No company profile found yet. Complete the form and save it to this workspace.</p>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
