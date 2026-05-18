import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

type FieldShellProps = {
  label: string;
  hint?: string;
  children: ReactNode;
};

export function FieldShell({ label, hint, children }: FieldShellProps) {
  return (
    <label className="grid gap-2">
      <span className="text-sm font-medium text-slate-700 dark:text-zinc-200">{label}</span>
      {children}
      {hint ? <span className="text-xs text-slate-500 dark:text-zinc-400">{hint}</span> : null}
    </label>
  );
}

const fieldClass =
  "h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-white/10 dark:bg-white/10 dark:text-white dark:placeholder:text-zinc-500";

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
};

export function Input({ label, hint, className = "", ...props }: InputProps) {
  return (
    <FieldShell label={label} hint={hint}>
      <input className={`${fieldClass} ${className}`} {...props} />
    </FieldShell>
  );
}

type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label: string;
  hint?: string;
};

export function Textarea({ label, hint, className = "", ...props }: TextareaProps) {
  return (
    <FieldShell label={label} hint={hint}>
      <textarea
        className={`${fieldClass} min-h-28 resize-y py-3 ${className}`}
        {...props}
      />
    </FieldShell>
  );
}

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  label: string;
  hint?: string;
};

export function Select({ label, hint, className = "", ...props }: SelectProps) {
  return (
    <FieldShell label={label} hint={hint}>
      <select className={`${fieldClass} ${className}`} {...props} />
    </FieldShell>
  );
}
