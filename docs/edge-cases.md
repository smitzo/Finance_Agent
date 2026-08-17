# Edge Cases and Failure Handling

## Covered business cases

| Case | Current handling | Primary control |
|---|---|---|
| Repeated bill ID | Reject intake with conflict | PostgreSQL lookup |
| Retried idempotency key | Return previously accepted bill | Tenant/workflow unique key |
| Repeated carrier bill number | Reject at intake or agent decision | Service lookup plus graph/rule checks |
| Missing carrier ID with similar name | Bounded fuzzy normalization | LLM service |
| Explicit unknown carrier ID | Deterministic error; skip ambiguity work | `check_carrier_known` |
| No contract for carrier/lane | Error finding | `check_contract_active(None, ...)` |
| Expired/future contract | Error finding | ISO-date comparisons |
| Multiple active contracts | Filter by date/minimum weight, then model or closest-rate fallback | `resolve_ambiguity` |
| Rate within 2% | Accept as match | Relative tolerance |
| Rate 2-5% away | Warning | `check_rate` |
| Rate more than 5% away | Error | `check_rate` |
| Minimum charge | Expected base is max(weight x rate, minimum) | `check_base_charge` |
| Revised surcharge | Select revised percentage on/after revision date | `check_fuel_surcharge` |
| FTL contract with kg bill | Use alternate kg rate when present; otherwise warn | `check_uom_mismatch` |
| Multiple BOLs | Sum actual weight | `check_weight_vs_bol` |
| Prior partial billing | Subtract prior connected bill weight | Graph context plus weight rule |
| Missing BOL | Warning and confidence reduction | `check_weight_vs_bol` |
| Overbilled weight | Hard error/dispute | Rule plus graph anomaly |
| Underbilled weight | Warning | Weight rule |
| Inconsistent total | Hard error; skip model | `check_total_amount` |
| Model unavailable | Deterministic fallback or no fuzzy match | LLM service |
| Model quota storm | Open cooldown circuit | Process-local circuit breaker |

## Infrastructure failures

| Failure | Current behavior | Recommended operational response |
|---|---|---|
| API restart after enqueue | Worker continues | Trace with correlation ID |
| Worker loss during task | Late-acked task is re-delivered | Check idempotency of side effects and duplicate audit entries |
| Redis unavailable | Enqueue fails; bill may remain pending | Alert and requeue pending bills; implement outbox |
| PostgreSQL unavailable | Health fails and processing cannot commit | Fail closed; restore database connectivity |
| Neo4j unavailable | Graph path fails for production backend | Alert; decide whether tenant policy permits relational fallback |
| LLM unavailable | Exact checks continue | Review increased unresolved/fuzzy cases |
| Review delayed | Durable checkpoint remains | Track queue age and service-level objective |
| Duplicate task delivery | Same bill can be processed twice today | Add processing lease/idempotent task state |

## Validation gaps to address

These are current limitations, not implemented safeguards:

- Bill and contract date strings are not strictly validated as real ISO dates at the API/model boundary.
- Currency is implicit; cross-currency invoices and exchange-rate evidence are not modelled.
- GST is checked only as part of internal total consistency, not recomputed from tax jurisdiction/rules.
- Negative values are blocked on API intake, but seed/database paths rely on trusted data.
- Tolerance is global, not currency-, carrier-, lane-, or rule-specific.
- Duplicate detection does not normalize punctuation/case in bill numbers.
- Global primary keys can collide across tenants even though reads are tenant scoped.
- Reviewer identity is not persisted from a production identity provider.
- A committed bill and its Celery message are not atomically coupled.
- Worker retries can repeat graph updates and audit persistence without a dedicated processing lease.
- Neo4j projection freshness has no stored watermark or reconciliation job.
- Bulk intake is bounded only by API request limits and per-item work; very large files need asynchronous import jobs.

## Recommended handling patterns

### Fail closed for money and identity

Unknown carrier, inconsistent total, unsupported workflow, missing tenant authorization, and malformed financial input should not be auto-approved.

### Degrade gracefully for optional intelligence

Model unavailability should never disable exact checks. Record the fallback used, reduce confidence when necessary, and route ambiguity to review.

### Make retries idempotent

Use idempotency keys at intake, unique event keys for audit writes, a processing lease/version on bills, and a transactional outbox for queue publication.

### Reconcile derived stores

Periodically compare PostgreSQL record counts/versions with Neo4j projection watermarks. Rebuild one tenant at a time without allowing workers to delete shared data concurrently.

### Test boundary values

For every tolerance or threshold, test immediately below, exactly at, and immediately above the boundary. Include zero/rounding, high-value invoices, multiple BOLs, prior billing, and provider-offline behavior.
