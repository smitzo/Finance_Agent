import type { ReactNode } from "react";
import { Card, CardBody } from "../ui/Card";

type StatCardProps = {
  label: string;
  value: string | number;
  detail: string;
  icon: ReactNode;
};

export function StatCard({ label, value, detail, icon }: StatCardProps) {
  return (
    <Card>
      <CardBody className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm text-slate-500 dark:text-zinc-400">{label}</p>
          <p className="mt-3 text-3xl font-semibold tracking-tight">{value}</p>
          <p className="mt-2 text-sm text-slate-500 dark:text-zinc-400">{detail}</p>
        </div>
        <div className="grid h-11 w-11 place-items-center rounded-xl bg-teal-500/10 text-teal-700 dark:text-teal-200">
          {icon}
        </div>
      </CardBody>
    </Card>
  );
}
