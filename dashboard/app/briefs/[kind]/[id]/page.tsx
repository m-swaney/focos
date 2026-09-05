import { BriefsShell } from "@/components/briefs/BriefsShell";

export const dynamic = "force-dynamic";

export default async function BriefPage({ params }: { params: Promise<{ kind: string; id: string }> }) {
  const { kind, id } = await params;
  return <BriefsShell kind={kind} id={id} />;
}
