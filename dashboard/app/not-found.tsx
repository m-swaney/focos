import Link from "next/link";
import { Card, PageHeader } from "@/components/ui";

export const dynamic = "force-dynamic";

export default function NotFound() {
  return (
    <>
      <PageHeader title="Not found" />
      <Card title="404" className="max-w-[480px]">
        <p className="text-[12px] text-secondary">Nothing lives at this address.</p>
        <Link href="/" className="mt-3 inline-block text-[12px] text-accent hover:underline">
          Back to Today
        </Link>
      </Card>
    </>
  );
}
