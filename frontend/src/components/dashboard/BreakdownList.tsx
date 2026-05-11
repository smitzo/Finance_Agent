import { Card, CardBody, CardHeader } from "../ui/Card";

type BreakdownListProps = {
  title: string;
  subtitle: string;
  values: Record<string, number>;
};

export function BreakdownList({ title, subtitle, values }: BreakdownListProps) {
  const entries = Object.entries(values);

  return (
    <Card>
      <CardHeader>
        <h2 className="font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-zinc-400">{subtitle}</p>
      </CardHeader>
      <CardBody className="grid gap-3">
        {entries.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between rounded-xl bg-slate-50 px-4 py-3 dark:bg-white/5">
            <span className="capitalize text-slate-600 dark:text-zinc-300">{label.replaceAll("_", " ")}</span>
            <span className="font-semibold">{value}</span>
          </div>
        ))}
        {!entries.length ? (
          <p className="rounded-xl bg-slate-50 px-4 py-6 text-center text-sm text-slate-500 dark:bg-white/5 dark:text-zinc-400">
            Nothing recorded yet.
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}
