import { HealthPanel } from "@/components/HealthPanel";
import { PageHeader, Section } from "@/components/ui";

export const dynamic = "force-dynamic";

export default function HealthPage() {
  return (
    <>
      <PageHeader title="Health" sub="what is connected, what last ran, and how to fix what is not" />
      <Section title="Checks">
        <HealthPanel />
      </Section>
    </>
  );
}
