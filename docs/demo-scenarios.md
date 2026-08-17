# Demo Scenario Catalogue

## Portfolio design

The demo is deterministic, synthetic, tenant-scoped, and safe to remove independently. It contains:

| Cohort | Count | Purpose |
|---|---:|---|
| Deterministic baseline | 60 | Complete carrier, contract, shipment, BOL, and correctly calculated bill |
| AI-assisted ambiguity | 40 | 20 known-carrier contract overlaps plus 20 fuzzy-carrier and contract-overlap cases |
| Edge and control cases | 20 | Exact failures, missing evidence, boundary behavior, and special pricing shapes |

Synthetic IDs use `DEMO-` and `CAR-DEMO` prefixes. Contact addresses use reserved `.example` domains.

## Edge-case matrix

| Scenario | Records | Evidence being exercised | Expected control path |
|---|---:|---|---|
| Rate outlier | 1 | Bill rate 45% above contract | Rate error and graph outlier; dispute |
| Weight overbill | 1 | Billed weight exceeds BOL | Weight error and graph anomaly; dispute |
| Duplicate number | 2 | One canonical bill plus a paired carrier-name-only duplicate | Canonical path remains valid; paired duplicate rejects |
| Total mismatch | 1 | Total differs from base + FSC + GST | Hard deterministic blocker; no LLM |
| Fuel surcharge mismatch | 1 | FSC is wrong while total remains internally consistent | FSC error |
| Expired contract | 1 | Contract status is expired | Contract error |
| Future contract | 1 | Bill predates effective date | Contract-date error |
| Minimum weight not met | 1 | Bill is below rate-row minimum | Eligibility error |
| Missing BOL | 1 | Shipment has no delivery evidence | Warning and confidence reduction |
| Missing shipment reference | 1 | Bill cannot traverse to shipment/BOL | Graph and BOL warnings; review path |
| No matching contract | 1 | Carrier and lane have no contract | No-contract error |
| UOM mismatch | 1 | Per-kg bill against FTL-only rate | Rate/UOM warnings; human review |
| Base-charge mismatch | 1 | Base differs from contracted calculation | Base-charge error |
| Rate warning | 1 | Rate differs by 3.5% | Warning rather than >5% hard error |
| Underbilled weight | 1 | Billed weight is below BOL total | Warning, not overbilling dispute |
| Unknown carrier | 1 | Explicit carrier ID absent from master data | Hard carrier error; dispute |
| Revised fuel surcharge | 1 | Revision is effective before bill date | Revised percentage accepted |
| Minimum charge applied | 1 | Weight x rate is below contractual minimum | Minimum charge accepted |
| Multiple BOLs | 1 | Two BOL weights support one bill | Aggregate weight accepted |

Each bill persists these fields inside `evidence`:

```json
{
  "demo": true,
  "demo_category": "edge",
  "demo_kind": "multiple_bols",
  "expected_behavior": "Aggregate multiple BOL records before comparing delivered and billed weight."
}
```

Agent findings are merged into this evidence after processing, preserving both the intended scenario and actual result.

## Loading the demo

Use the demo workspace:

```text
Tenant:   demo
Username: demo
Password: demo
```

Then choose **Use demo data** in the overview, or call:

```bash
curl -u demo:demo -X POST \
  -H 'X-Tenant-ID: demo' \
  http://localhost:8000/admin/demo/load
```

The response includes accurate deterministic, LLM, and edge-case bill ID lists plus a `scenario_catalog` mapping each ID to its intended behavior.

Track execution:

```bash
docker compose logs -f worker

curl -u demo:demo \
  -H 'X-Tenant-ID: demo' \
  http://localhost:8000/metrics
```

The endpoint returns `202` because processing is asynchronous. Wait until `pending` and `processing` reach zero before evaluating final distributions.

## Provider-offline behavior

Without an OpenAI or Anthropic key:

- all exact rules continue;
- known-carrier overlapping contracts use the closest-rate fallback;
- fuzzy carrier names cannot be normalized by a provider and can become unknown-carrier disputes before contract selection;
- explanations use deterministic fallback text.

This degraded behavior is intentional and should be visible when interpreting demo outcomes.

## Cleanup

```bash
curl -u demo:demo -X DELETE \
  -H 'X-Tenant-ID: demo' \
  http://localhost:8000/admin/demo
```

Cleanup deletes only demo-prefixed records in the selected tenant, then rebuilds that tenant's graph. It does not remove migrations, non-demo records, or Compose volumes.

## What the demo does not prove

- production throughput or latency;
- model accuracy on real carrier names;
- tax or currency correctness beyond implemented rules;
- production identity/security readiness;
- long-running queue recovery under infrastructure failure;
- calibration of confidence thresholds on historical outcomes.

Those require separate integration, load, security, and labelled-quality validation.
