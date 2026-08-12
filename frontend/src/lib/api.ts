import type { AuditEvent, CompanyDraft, CompanyProfile, FreightBill, Metrics, NewFreightBill, PartnerDraft, PartnerFirm, SessionProfile, UserSession } from "../types";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

type RequestOptions = RequestInit & {
  session: UserSession;
};

function authHeader(session: UserSession) {
  return `Basic ${btoa(`${session.username}:${session.password}`)}`;
}

async function request<T>(path: string, { session, headers, ...options }: RequestOptions): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      Authorization: authHeader(session),
      "X-Tenant-ID": session.tenantId,
      "Content-Type": "application/json",
      ...headers,
    },
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export const api = {
  session: (session: UserSession) => request<SessionProfile>("/session", { session }),
  metrics: (session: UserSession) => request<Metrics>("/metrics", { session }),
  bills: (session: UserSession, limit = 100) => request<FreightBill[]>(`/freight-bills?limit=${limit}`, { session }),
  bill: (session: UserSession, id: string) => request<FreightBill>(`/freight-bills/${id}`, { session }),
  audit: (session: UserSession, id: string) => request<AuditEvent[]>(`/freight-bills/${id}/audit`, { session }),
  reviewQueue: (session: UserSession) => request<FreightBill[]>("/review-queue?limit=100", { session }),
  createBill: (session: UserSession, bill: NewFreightBill) => request<{ id: string; status: string; message: string }>("/freight-bills", {
    session,
    method: "POST",
    body: JSON.stringify(bill),
  }),
  submitReview: (session: UserSession, id: string, decision: string, notes: string) => request<{ id: string; message: string }>(`/review/${id}`, {
    session,
    method: "POST",
    body: JSON.stringify({ reviewer_decision: decision, reviewer_notes: notes }),
  }),
  company: (session: UserSession) => request<CompanyProfile | null>("/company", { session }),
  saveCompany: (session: UserSession, draft: CompanyDraft) => request<CompanyProfile>("/company", {
    session,
    method: "PUT",
    body: JSON.stringify({
      legal_name: draft.legalName,
      display_name: draft.displayName,
      gstin: draft.gstin || null,
      billing_email: draft.billingEmail,
      timezone: draft.timezone,
      country: "IN",
    }),
  }),
  partners: (session: UserSession) => request<PartnerFirm[]>("/partner-firms", { session }),
  savePartner: (session: UserSession, draft: PartnerDraft) => request<PartnerFirm>("/partner-firms", {
    session,
    method: "POST",
    body: JSON.stringify({
      name: draft.name,
      registration_number: draft.registrationNumber || null,
      gstin: draft.gstin || null,
      contact_name: draft.contactName,
      contact_email: draft.contactEmail,
      contact_phone: draft.contactPhone || null,
    }),
  }),
  loadDemo: (session: UserSession) => request<{ status: string }>("/admin/demo/load", { session, method: "POST" }),
  deleteDemo: (session: UserSession) => request<{ status: string }>("/admin/demo", { session, method: "DELETE" }),
};
