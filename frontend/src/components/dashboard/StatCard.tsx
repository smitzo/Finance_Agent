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
    <Card className="transition hover:-translate-y-0.5 hover:shadow-md">
      <CardBody className="flex items-start justify-between gap-4 p-5">
        <div>
          <p className="text-sm text-slate-500 dark:text-zinc-400">{label}</p>
          <p className="mt-3 text-2xl font-semibold tracking-[-0.03em]">{value}</p>
          <p className="mt-2 text-sm text-slate-500 dark:text-zinc-400">{detail}</p>
        </div>
        <div className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-50 text-emerald-700 dark:bg-[#d8ff5f]/10 dark:text-[#d8ff5f]">
          {icon}
        </div>
      </CardBody>
    </Card>
  );
}
