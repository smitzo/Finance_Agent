type PageTitleProps = {
  eyebrow: string;
  title: string;
  description: string;
};

export function PageTitle({ eyebrow, title, description }: PageTitleProps) {
  return (
    <div>
      <p className="text-sm font-semibold uppercase tracking-[0.22em] text-teal-600 dark:text-teal-300">{eyebrow}</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500 dark:text-zinc-400">{description}</p>
    </div>
  );
}
