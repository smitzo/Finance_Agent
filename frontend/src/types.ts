export type AuthMode = "login" | "signup";

export type UserSession = {
  username: string;
  password: string;
  tenantId: string;
};

export type CompanyDraft = {
  legalName: string;
  displayName: string;
  gstin: string;
  billingEmail: string;
  timezone: string;
};

export type PartnerDraft = {
  name: string;
  registrationNumber: string;
  gstin: string;
  contactName: string;
  contactEmail: string;
  contactPhone: string;
};

export type FreightBill = {
  id: string;
  tenant_id: string;
  workflow_type: string;
  carrier_name: string;
  bill_number: string;
  lane: string;
  total_amount: number;
  status: string;
  confidence_score: number | null;
  decision: string | null;
};

export type Metrics = {
  tenant_id: string;
  total_bills: number;
  by_status: Record<string, number>;
  by_decision: Record<string, number>;
  avg_confidence_score: number | null;
};

export type CompanyProfile = {
  id: string;
  tenant_id: string;
  legal_name: string;
  display_name: string;
  gstin: string | null;
  country: string;
  timezone: string;
  billing_email: string;
  status: string;
  ca_partner_firm: PartnerFirm | null;
};

export type PartnerFirm = {
  id: string;
  name: string;
  firm_type: string;
  registration_number: string | null;
  gstin: string | null;
  contact_name: string;
  contact_email: string;
  contact_phone: string | null;
  status: string;
};
