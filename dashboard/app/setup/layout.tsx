import { Rail } from "@/components/setup/Rail";

export const dynamic = "force-dynamic";

export default function SetupLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-6">
      <Rail />
      <div className="min-w-0">{children}</div>
    </div>
  );
}
