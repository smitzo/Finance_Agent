import demoBatchData from "../../demo/demo-bills.json";

export type DemoScenarioId = "clean" | "contract" | "weight" | "duplicate" | "total" | "carrier";

export type DemoBillInput = {
  demo_scenario?: DemoScenarioId;
  id: string;
  carrier_id?: string;
  carrier_name: string;
  bill_number: string;
  bill_date: string;
  shipment_reference?: string;
  lane: string;
  billed_weight_kg: number;
  rate_per_kg: number;
  billing_unit: string;
  base_charge: number;
  fuel_surcharge: number;
  gst_amount: number;
  total_amount: number;
};

type DemoContract = {
  id: string;
  rate_per_kg: number;
  fuel_surcharge_percent: number;
  effective_date: string;
  expiry_date: string;
  tier: string;
};

type DemoReference = {
  carrier: { id: string; name: string } | null;
  contracts: DemoContract[];
  shipment: { id: string; status: string; lane: string } | null;
  bols: Array<{ id: string; actual_weight_kg: number }>;
  duplicate_bill_ids: string[];
};

export type DemoScenario = {
  id: DemoScenarioId;
  name: string;
  eyebrow: string;
  description: string;
  bill: DemoBillInput;
  reference: DemoReference;
};

export type DemoFinding = {
  code: string;
  severity: "ok" | "warn" | "error";
  message: string;
};

export type DemoStage = {
  id: "intake" | "queue" | "graph" | "rules" | "model" | "decision" | "persist";
  label: string;
  service: string;
  detail: string;
  request?: unknown;
  response?: unknown;
  skipped?: boolean;
};

export type DemoGraphNode = {
  id: string;
  label: string;
  meta: string;
  kind: "bill" | "carrier" | "contract" | "lane" | "shipment" | "bol" | "missing";
  x: number;
  y: number;
};

export type DemoGraphEdge = {
  from: string;
  to: string;
  label: string;
};

export type DemoRun = {
  bill: DemoBillInput;
  stages: DemoStage[];
  findings: DemoFinding[];
  confidence: number;
  decision: "auto_approve" | "flag" | "dispute" | "reject";
  status: "approved" | "awaiting_review" | "disputed" | "rejected";
  explanation: string;
  chosenContract: DemoContract | null;
  graphQuery: string;
  graphNodes: DemoGraphNode[];
  graphEdges: DemoGraphEdge[];
  modelExchange: { prompt: unknown; response: unknown } | null;
  finalOutput: Record<string, unknown>;
};

const baseBill: DemoBillInput = {
  id: "DEMO-FB-LIVE-001",
  carrier_id: "CAR-DEMO-ATLAS",
  carrier_name: "Demo Atlas Freight",
  bill_number: "DEMO/INV/2026/001",
  bill_date: "2026-08-17",
  shipment_reference: "DEMO-SHP-DEL-BLR-001",
  lane: "DEL-BLR",
  billed_weight_kg: 850,
  rate_per_kg: 15,
  billing_unit: "kg",
  base_charge: 12750,
  fuel_surcharge: 1020,
  gst_amount: 2479,
  total_amount: 16249,
};

const standardContract: DemoContract = {
  id: "DEMO-CC-ATLAS-STANDARD",
  rate_per_kg: 13.65,
  fuel_surcharge_percent: 8,
  effective_date: "2026-01-01",
  expiry_date: "2026-12-31",
  tier: "Standard road",
};

const premiumContract: DemoContract = {
  id: "DEMO-CC-ATLAS-PREMIUM",
  rate_per_kg: 15,
  fuel_surcharge_percent: 8,
  effective_date: "2026-01-01",
  expiry_date: "2026-12-31",
  tier: "Priority express",
};

const baseReference: DemoReference = {
  carrier: { id: "CAR-DEMO-ATLAS", name: "Demo Atlas Freight" },
  contracts: [premiumContract],
  shipment: { id: "DEMO-SHP-DEL-BLR-001", status: "delivered", lane: "DEL-BLR" },
  bols: [{ id: "DEMO-BOL-DEL-BLR-001", actual_weight_kg: 850 }],
  duplicate_bill_ids: [],
};

export const demoScenarios: DemoScenario[] = [
  {
    id: "clean",
    name: "Clean invoice",
    eyebrow: "Auto approval",
    description: "Every charge and delivery record agrees with one active contract.",
    bill: baseBill,
    reference: baseReference,
  },
  {
    id: "contract",
    name: "Contract ambiguity",
    eyebrow: "Bounded model reasoning",
    description: "Two contracts cover the lane; the model may choose only from those graph results.",
    bill: { ...baseBill, id: "DEMO-FB-LIVE-002", bill_number: "DEMO/INV/2026/002" },
    reference: { ...baseReference, contracts: [standardContract, premiumContract] },
  },
  {
    id: "weight",
    name: "Weight overbilling",
    eyebrow: "Deterministic dispute",
    description: "The invoice claims 850 kg while connected delivery evidence proves only 590 kg.",
    bill: { ...baseBill, id: "DEMO-FB-LIVE-003", bill_number: "DEMO/INV/2026/003" },
    reference: { ...baseReference, bols: [{ id: "DEMO-BOL-DEL-BLR-003", actual_weight_kg: 590 }] },
  },
  {
    id: "duplicate",
    name: "Duplicate invoice",
    eyebrow: "Immediate rejection",
    description: "The carrier bill number already exists in the tenant evidence graph.",
    bill: { ...baseBill, id: "DEMO-FB-LIVE-004" },
    reference: { ...baseReference, duplicate_bill_ids: ["DEMO-FB-PAID-884"] },
  },
  {
    id: "total",
    name: "Inconsistent total",
    eyebrow: "Human review",
    description: "The submitted total does not equal base charge, surcharge, and tax.",
    bill: { ...baseBill, id: "DEMO-FB-LIVE-005", bill_number: "DEMO/INV/2026/005", total_amount: 17999 },
    reference: baseReference,
  },
  {
    id: "carrier",
    name: "Unknown carrier",
    eyebrow: "Master-data control",
    description: "A submitted carrier identifier cannot be resolved to tenant reference data.",
    bill: {
      ...baseBill,
      id: "DEMO-FB-LIVE-006",
      bill_number: "DEMO/INV/2026/006",
      carrier_id: "CAR-NOT-IN-MASTER",
      carrier_name: "Unregistered Express",
    },
    reference: { carrier: null, contracts: [], shipment: null, bols: [], duplicate_bill_ids: [] },
  },
];

export const demoBatchBills = demoBatchData as DemoBillInput[];

function closeEnough(actual: number, expected: number) {
  if (expected === 0) return actual === 0;
  return Math.abs(actual - expected) / expected <= 0.02;
}

function finding(code: string, severity: DemoFinding["severity"], message: string): DemoFinding {
  return { code, severity, message };
}

function buildGraph(bill: DemoBillInput, reference: DemoReference) {
  const nodes: DemoGraphNode[] = [
    { id: "bill", label: bill.id, meta: `₹${bill.total_amount.toLocaleString("en-IN")}`, kind: "bill", x: 78, y: 210 },
    reference.carrier
      ? { id: "carrier", label: reference.carrier.name, meta: reference.carrier.id, kind: "carrier", x: 260, y: 76 }
      : { id: "carrier", label: "No carrier match", meta: bill.carrier_id ?? "missing ID", kind: "missing", x: 260, y: 76 },
    { id: "lane", label: bill.lane, meta: "Lane", kind: "lane", x: 665, y: 92 },
  ];
  const edges: DemoGraphEdge[] = [];

  if (reference.carrier) edges.push({ from: "bill", to: "carrier", label: "BILLED_BY" });
  reference.contracts.forEach((contract, index) => {
    const id = `contract-${index}`;
    nodes.push({
      id,
      label: contract.id.replace("DEMO-CC-ATLAS-", ""),
      meta: `₹${contract.rate_per_kg}/kg · ${contract.tier}`,
      kind: "contract",
      x: 460,
      y: reference.contracts.length > 1 ? 45 + index * 105 : 92,
    });
    edges.push({ from: "carrier", to: id, label: "HAS_CONTRACT" });
    edges.push({ from: id, to: "lane", label: "COVERS_LANE" });
  });

  if (reference.shipment) {
    nodes.push({ id: "shipment", label: reference.shipment.id, meta: reference.shipment.status, kind: "shipment", x: 285, y: 310 });
    edges.push({ from: "bill", to: "shipment", label: "REFERENCES" });
  }
  reference.bols.forEach((bol, index) => {
    const id = `bol-${index}`;
    nodes.push({ id, label: bol.id, meta: `${bol.actual_weight_kg} kg delivered`, kind: "bol", x: 535, y: 318 + index * 68 });
    edges.push({ from: "shipment", to: id, label: "HAS_BOL" });
  });
  return { nodes, edges };
}

export function processDemoBill(bill: DemoBillInput, scenario: DemoScenario): DemoRun {
  const reference = scenario.reference;
  const findings: DemoFinding[] = [];

  findings.push(reference.duplicate_bill_ids.length
    ? finding("DUPLICATE_BILL", "error", `Bill number already exists as ${reference.duplicate_bill_ids.join(", ")}.`)
    : finding("NO_DUPLICATE", "ok", "No duplicate carrier bill number found."));
  findings.push(reference.carrier
    ? finding("CARRIER_KNOWN", "ok", `Carrier resolved to ${reference.carrier.id}.`)
    : finding("UNKNOWN_CARRIER", "error", `Carrier ${bill.carrier_id ?? bill.carrier_name} is not in tenant master data.`));

  const expectedTotal = Math.round((bill.base_charge + bill.fuel_surcharge + bill.gst_amount) * 100) / 100;
  findings.push(closeEnough(bill.total_amount, expectedTotal)
    ? finding("TOTAL_CONSISTENT", "ok", `Total ₹${bill.total_amount} equals base + surcharge + tax.`)
    : finding("TOTAL_INCONSISTENT", "error", `Total ₹${bill.total_amount} does not equal ₹${expectedTotal}.`));

  const bolWeight = reference.bols.reduce((sum, bol) => sum + bol.actual_weight_kg, 0);
  if (!reference.bols.length) {
    findings.push(finding("NO_BOL", "warn", "No bill of lading is connected to this invoice."));
  } else if (bill.billed_weight_kg > bolWeight * 1.02) {
    findings.push(finding("WEIGHT_MISMATCH", "error", `Billed ${bill.billed_weight_kg} kg exceeds BOL evidence of ${bolWeight} kg.`));
  } else if (!closeEnough(bill.billed_weight_kg, bolWeight)) {
    findings.push(finding("WEIGHT_MISMATCH", "warn", `Billed ${bill.billed_weight_kg} kg is below BOL evidence of ${bolWeight} kg.`));
  } else {
    findings.push(finding("WEIGHT_MATCH", "ok", `Billed weight agrees with ${bolWeight} kg of BOL evidence.`));
  }

  let chosenContract: DemoContract | null = null;
  let modelExchange: DemoRun["modelExchange"] = null;
  if (reference.contracts.length) {
    chosenContract = reference.contracts.reduce((best, candidate) =>
      Math.abs(candidate.rate_per_kg - bill.rate_per_kg) < Math.abs(best.rate_per_kg - bill.rate_per_kg)
        ? candidate
        : best,
    );
    if (reference.contracts.length > 1) {
      modelExchange = {
        prompt: {
          task: "Choose exactly one supplied contract; do not calculate invoice totals.",
          bill: { lane: bill.lane, rate_per_kg: bill.rate_per_kg, billed_weight_kg: bill.billed_weight_kg },
          allowed_contracts: reference.contracts.map(({ id, rate_per_kg, tier }) => ({ id, rate_per_kg, tier })),
        },
        response: {
          chosen_contract_id: chosenContract.id,
          reasoning: `${chosenContract.tier} is the closest permitted rate match for the submitted bill.`,
          simulated: true,
        },
      };
    }
    findings.push(closeEnough(bill.rate_per_kg, chosenContract.rate_per_kg)
      ? finding("RATE_MATCH", "ok", `Billed ₹${bill.rate_per_kg}/kg matches ${chosenContract.id}.`)
      : finding("RATE_MISMATCH", "error", `Billed ₹${bill.rate_per_kg}/kg differs from contracted ₹${chosenContract.rate_per_kg}/kg.`));
    const expectedBase = Math.round(bill.billed_weight_kg * chosenContract.rate_per_kg * 100) / 100;
    findings.push(closeEnough(bill.base_charge, expectedBase)
      ? finding("BASE_CHARGE_MATCH", "ok", `Base charge agrees with weight × contracted rate.`)
      : finding("BASE_CHARGE_MISMATCH", "error", `Base charge should be ₹${expectedBase}.`));
  } else {
    findings.push(finding("NO_CONTRACT", "error", "No carrier contract covers the submitted lane."));
  }

  const uniqueFindings = Array.from(new Map(findings.map((item) => [item.code, item])).values());
  const errors = uniqueFindings.filter((item) => item.severity === "error");
  const warnings = uniqueFindings.filter((item) => item.severity === "warn");
  let confidence = Math.max(0, Math.min(1, 1 - errors.length * 0.25 - warnings.length * 0.08));
  if (reference.contracts.length > 1) confidence -= 0.15;
  confidence = Math.round(Math.max(0, confidence) * 1000) / 1000;

  const errorCodes = new Set(errors.map((item) => item.code));
  let decision: DemoRun["decision"];
  if (errorCodes.has("DUPLICATE_BILL")) decision = "reject";
  else if (confidence >= 0.85 && errors.length === 0) decision = "auto_approve";
  else if (confidence <= 0.4 || ["UNKNOWN_CARRIER", "WEIGHT_MISMATCH"].some((code) => errorCodes.has(code))) decision = "dispute";
  else decision = "flag";

  const statusMap: Record<DemoRun["decision"], DemoRun["status"]> = {
    auto_approve: "approved",
    flag: "awaiting_review",
    dispute: "disputed",
    reject: "rejected",
  };
  const status = statusMap[decision];
  const topIssue = errors[0]?.message;
  const explanation = topIssue
    ? `${bill.id} is ${status.replace("_", " ")} because ${topIssue.toLowerCase()}`
    : `${bill.id} is approved after contract, rate, charge, weight, duplicate, and total controls completed.`;

  const graphQuery = `MATCH (c:Carrier {tenant_id: $tenant_id, id: $carrier_id})\n` +
    `OPTIONAL MATCH (c)-[:HAS_CONTRACT]->(cc:Contract)-[r:COVERS_LANE]->(:Lane {lane: $lane})\n` +
    `OPTIONAL MATCH (fb:FreightBill {bill_number: $bill_number})-[:REFERENCES]->(s:Shipment)-[:HAS_BOL]->(bol:BOL)\n` +
    `RETURN c, collect(DISTINCT cc) AS contracts, s, collect(DISTINCT bol) AS bols`;
  const { nodes: graphNodes, edges: graphEdges } = buildGraph(bill, reference);

  const finalOutput = {
    id: bill.id,
    status,
    decision,
    confidence_score: confidence,
    chosen_contract: chosenContract?.id ?? null,
    findings: uniqueFindings,
    explanation,
    evidence: {
      carrier: reference.carrier,
      shipment: reference.shipment,
      bol_count: reference.bols.length,
      duplicate_bill_ids: reference.duplicate_bill_ids,
    },
  };

  const stages: DemoStage[] = [
    {
      id: "intake",
      label: "Validate API input",
      service: "FastAPI",
      detail: "Schema, tenant, idempotency, and correlation metadata are checked.",
      request: { method: "POST", path: "/freight-bills", body: bill },
      response: { status: 202, bill_id: bill.id, correlation_id: "demo-trace-7f8c" },
    },
    {
      id: "queue",
      label: "Persist and enqueue",
      service: "PostgreSQL → Redis → Celery",
      detail: "The bill is committed before a durable worker task is published.",
      request: { task: "freightflow.process_bill", bill_id: bill.id },
      response: { task_id: "demo-task-c41a", state: "queued" },
    },
    {
      id: "graph",
      label: "Traverse evidence graph",
      service: "Neo4j / Cypher",
      detail: "Carrier, contracts, lane, shipment, BOL, and duplicate relationships are loaded.",
      request: { query: graphQuery, parameters: { tenant_id: "demo", carrier_id: bill.carrier_id, lane: bill.lane, bill_number: bill.bill_number } },
      response: { carrier: reference.carrier, contracts: reference.contracts, shipment: reference.shipment, bols: reference.bols, duplicate_bill_ids: reference.duplicate_bill_ids },
    },
    {
      id: "rules",
      label: "Run financial controls",
      service: "Deterministic Python rules",
      detail: "Exact totals, rates, charges, weights, dates, and duplicates stay outside the model.",
      request: { bill_id: bill.id, evidence_snapshot: true },
      response: { findings: uniqueFindings },
    },
    {
      id: "model",
      label: modelExchange ? "Resolve bounded ambiguity" : "Model call not required",
      service: modelExchange ? "LLM adapter" : "Policy guard",
      detail: modelExchange ? "The model chooses only from graph-supplied contract IDs." : "Deterministic evidence is sufficient, so cost and hallucination risk are avoided.",
      request: modelExchange?.prompt,
      response: modelExchange?.response ?? { skipped: true, reason: "No ambiguity requiring language reasoning" },
      skipped: !modelExchange,
    },
    {
      id: "decision",
      label: "Score and route",
      service: "LangGraph decision node",
      detail: "Findings become an explainable confidence score and workflow decision.",
      request: { errors: errors.length, warnings: warnings.length, ambiguity_penalty: reference.contracts.length > 1 ? 0.15 : 0 },
      response: { confidence, decision, next: decision === "flag" ? "human_review" : "finalize" },
    },
    {
      id: "persist",
      label: "Persist final output",
      service: "PostgreSQL + audit log",
      detail: "Decision, evidence, explanation, and timeline are stored for reconstruction.",
      request: { bill_id: bill.id, decision },
      response: finalOutput,
    },
  ];

  return {
    bill,
    stages,
    findings: uniqueFindings,
    confidence,
    decision,
    status,
    explanation,
    chosenContract,
    graphQuery,
    graphNodes,
    graphEdges,
    modelExchange,
    finalOutput,
  };
}

export function scenarioById(id: DemoScenarioId) {
  return demoScenarios.find((scenario) => scenario.id === id) ?? demoScenarios[0];
}
