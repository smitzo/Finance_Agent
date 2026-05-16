import { Radar } from "lucide-react";
import type { FreightBill } from "../../types";
import { formatPercent } from "../../lib/format";
import { Card, CardBody, CardHeader } from "../ui/Card";

export function AnomalyRadar({ bills }: { bills: FreightBill[] }) {
  const riskyBills = bills.filter((bill) =>
    ["disputed", "rejected", "awaiting_review"].includes(bill.status) || (bill.confidence_score ?? 1) < 0.75,
  );

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Radar className="h-5 w-5 text-teal-600 dark:text-teal-300" />
          <div>
            <h2 className="font-semibold">Anomaly radar</h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-zinc-400">Bills that deserve a closer graph review.</p>
          </div>
        </div>
      </CardHeader>
      <CardBody className="grid gap-3">
        {riskyBills.slice(0, 4).map((bill) => (
          <div key={bill.id} className="rounded-xl bg-slate-50 p-4 dark:bg-white/5">
            <div className="flex items-center justify-between gap-3">
              <p className="font-medium">{bill.bill_number}</p>
              <p className="text-sm text-rose-600 dark:text-rose-300">
                {formatPercent(bill.confidence_score)}
              </p>
            </div>
            <p className="mt-1 text-sm text-slate-500 dark:text-zinc-400">{bill.carrier_name} · {bill.lane}</p>
          </div>
        ))}
        {!riskyBills.length ? (
          <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500 dark:bg-white/5 dark:text-zinc-400">
            No active anomalies in the latest slice.
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}
