import Link from "next/link";
import { api } from "@/lib/api";
import { ErrorState, Section } from "@/components/primitives";

export const dynamic = "force-dynamic";

export default async function ResearchProjectsPage() {
  let error = "";
  let rows: { id: string; title: string; industry: string; status: string; updated_at: string }[] = [];
  try {
    const response = await api.researchProjects();
    if (!response.ok) error = response.error_message || "研究底稿没打开";
    else rows = response.rows || [];
  } catch (err) {
    error = (err as Error).message;
  }

  return (
    <Section title="研究底稿" note="一条行业问题对应一个项目。Thesis 按版本留着，不覆盖。">
      <p>
        <Link href="/research/new">新研究</Link>
      </p>
      {error ? <ErrorState message={error} /> : null}
      {rows.length ? (
        <table>
          <thead>
            <tr>
              <th>项目</th>
              <th>行业</th>
              <th>状态</th>
              <th>更新</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <Link href={`/research/projects/${row.id}`}>{row.title || row.id}</Link>
                  <div className="code">{row.id}</div>
                </td>
                <td>{row.industry || "—"}</td>
                <td>{row.status}</td>
                <td className="muted">{(row.updated_at || "").slice(0, 16)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">还没有项目。</p>
      )}
    </Section>
  );
}
