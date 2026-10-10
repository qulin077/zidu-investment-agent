import { ResearchBoard } from "../projects/[id]/page";

export const dynamic = "force-dynamic";

export default async function ResearchByIdPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return ResearchBoard({ id: projectId });
}
