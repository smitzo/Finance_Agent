import { PackageCheck, Truck } from "lucide-react";

type TruckLoaderProps = {
  label?: string;
};

export function TruckLoader({ label = "Routing freight intelligence..." }: TruckLoaderProps) {
  return (
    <div className="grid gap-3">
      <div className="relative h-12 overflow-hidden rounded-xl border border-slate-200 bg-slate-100 dark:border-white/10 dark:bg-white/10">
        <div className="absolute inset-x-4 top-1/2 border-t border-dashed border-slate-300 dark:border-white/20" />
        <div className="animate-[drive_1.8s_ease-in-out_infinite] absolute left-4 top-1/2 -translate-y-1/2">
          <div className="flex items-center gap-1 rounded-lg bg-teal-600 px-2 py-1 text-white shadow-lg shadow-teal-700/20 dark:bg-teal-400 dark:text-zinc-950">
            <Truck className="h-5 w-5" />
            <PackageCheck className="h-4 w-4" />
          </div>
        </div>
      </div>
      <p className="text-sm text-slate-500 dark:text-zinc-400">{label}</p>
    </div>
  );
}
