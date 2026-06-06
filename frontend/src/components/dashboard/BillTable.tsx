import { FileSearch } from "lucide-react";
import { EmptyState } from "../common/EmptyState";
import type { FreightBill } from "../../types";
import { formatCurrency, formatPercent } from "../../lib/format";
import { Badge } from "../ui/Badge";
import { Card, CardBody, CardHeader } from "../ui/Card";

function statusTone(status: string) {
  if (status === "approved") return "good";
  if (status === "awaiting_review" || status === "processing") return "warn";
  if (status === "disputed" || status === "rejected") return "danger";
  return "neutral";
}

export function BillTable({ bills }: { bills: FreightBill[] }) {
  return (
    <Card>
      <CardHeader>
        <h2 className="font-semibold">Recent freight bills</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-zinc-400">Latest workflow activity across the selected tenant.</p>
      </CardHeader>
      <CardBody className="overflow-x-auto p-0">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500 dark:border-white/10 dark:text-zinc-400">
            <tr>
              <th className="px-5 py-3">Bill</th>
              <th className="px-5 py-3">Carrier</th>
              <th className="px-5 py-3">Lane</th>
              <th className="px-5 py-3">Amount</th>
              <th className="px-5 py-3">Confidence</th>
              <th className="px-5 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {bills.map((bill) => (
              <tr key={bill.id} className="border-b border-slate-100 last:border-0 dark:border-white/5">
                <td className="px-5 py-4">
                  <p className="font-medium">{bill.id}</p>
                  <p className="text-xs text-slate-500 dark:text-zinc-400">{bill.bill_number}</p>
                </td>
                <td className="px-5 py-4">{bill.carrier_name}</td>
                <td className="px-5 py-4">{bill.lane}</td>
                <td className="px-5 py-4">{formatCurrency(bill.total_amount)}</td>
                <td className="px-5 py-4">{formatPercent(bill.confidence_score)}</td>
                <td className="px-5 py-4">
                  <Badge tone={statusTone(bill.status)}>{bill.status.replaceAll("_", " ")}</Badge>
                </td>
              </tr>
            ))}
            {!bills.length ? (
              <tr>
                <td className="p-5" colSpan={6}>
                  <EmptyState
                    icon={<FileSearch className="h-5 w-5" />}
                    title="No freight bills yet"
                    description="Load demo data to see the validation workflow and graph anomaly radar."
                  />
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}
