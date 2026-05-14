import { CheckCircle2, Circle } from "lucide-react";
import { Card, CardBody } from "../ui/Card";

type Step = {
  label: string;
  complete: boolean;
};

export function OnboardingProgress({ steps }: { steps: Step[] }) {
  const completeCount = steps.filter((step) => step.complete).length;

  return (
    <Card>
      <CardBody>
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="font-semibold">Workspace readiness</h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-zinc-400">
              {completeCount} of {steps.length} setup signals complete.
            </p>
          </div>
          <div className="text-2xl font-semibold">{Math.round((completeCount / steps.length) * 100)}%</div>
        </div>
        <div className="mt-4 grid gap-2">
          {steps.map((step) => {
            const Icon = step.complete ? CheckCircle2 : Circle;
            return (
              <div key={step.label} className="flex items-center gap-2 text-sm">
                <Icon className={`h-4 w-4 ${step.complete ? "text-emerald-500" : "text-slate-400 dark:text-zinc-500"}`} />
                <span className={step.complete ? "text-slate-700 dark:text-zinc-200" : "text-slate-500 dark:text-zinc-400"}>{step.label}</span>
              </div>
            );
          })}
        </div>
      </CardBody>
    </Card>
  );
}
