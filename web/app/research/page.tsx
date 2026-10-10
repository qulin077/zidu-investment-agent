import { Suspense } from "react";
import { ResearchWorkspace } from "./workspace";

export const dynamic = "force-dynamic";

export default function ResearchPage() {
  return (
    <Suspense fallback={<p className="section-note">正在打开研究会话。</p>}>
      <ResearchWorkspace />
    </Suspense>
  );
}
