import type { CompanyProfile, FreightBill, Metrics, PartnerFirm, UserSession } from "../types";

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
  metrics: (session: UserSession) => request<Metrics>("/metrics", { session }),
  bills: (session: UserSession) => request<FreightBill[]>("/freight-bills?limit=12", { session }),
  company: (session: UserSession) => request<CompanyProfile | null>("/company", { session }),
  partners: (session: UserSession) => request<PartnerFirm[]>("/partner-firms", { session }),
  loadDemo: (session: UserSession) => request<{ status: string }>("/admin/demo/load", { session, method: "POST" }),
  deleteDemo: (session: UserSession) => request<{ status: string }>("/admin/demo", { session, method: "DELETE" }),
};
