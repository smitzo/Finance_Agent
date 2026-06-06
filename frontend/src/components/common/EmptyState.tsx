import type { ReactNode } from "react";

type EmptyStateProps = {
  icon: ReactNode;
  title: string;
  description: string;
};

export function EmptyState({ icon, title, description }: EmptyStateProps) {
  return (
    <div className="grid place-items-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-6 py-10 text-center dark:border-white/10 dark:bg-white/5">
      <div className="grid h-12 w-12 place-items-center rounded-xl bg-white text-teal-600 shadow-sm dark:bg-white/10 dark:text-teal-200">
        {icon}
      </div>
      <h3 className="mt-4 font-semibold">{title}</h3>
      <p className="mt-2 max-w-sm text-sm text-slate-500 dark:text-zinc-400">{description}</p>
    </div>
  );
}
