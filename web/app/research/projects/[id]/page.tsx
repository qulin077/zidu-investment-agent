import Link from "next/link";
import { notFound } from "next/navigation";
import { API_BASE, api, type ResearchProjectView } from "@/lib/api";
import { Section } from "@/components/primitives";

export const dynamic = "force-dynamic";

const CLAIM_ORDER = ["FACT", "ESTIMATE", "INFERENCE", "OPINION"];

export async function ResearchBoard({ id }: { id: string }) {
  let view: ResearchProjectView;
  try {
    view = await api.researchProject(id);
  } catch {
    notFound();
  }
  const thesis = view.thesis || {};
  const claims = view.claims || {};
  const activity = await projectActivity(id);

  return (
    <>
      <Section
        title={view.project?.title || id}
        note={`${view.project?.question || ""} · Thesis ${thesis.id || ""} v${thesis.version || ""} · as_of ${thesis.as_of || "—"}`}
      >
        <p className="section-note">研究框架，非投资建议。判断和事实分开列。</p>
        <p>{view.project?.industry_definition}</p>
        <p>
          <Link href="/research/projects">全部项目</Link>
        </p>
      </Section>

      <Section title="Research Run" note="波次、任务和来源。不是聊天框。">
        <ul>
          {(view.waves || []).map((row) => (
            <li key={row.name}>
              Wave {row.wave} / 4 · {row.name}
            </li>
          ))}
        </ul>
        <p className="muted">
          反证 {view.disconfirmation?.length || 0} · Claim 关系 {view.claim_relations?.length || 0}
        </p>
        {(view.disconfirmation || []).map((row) => (
          <p key={row.query}>
            {row.status} · {row.result}
            <span className="muted"> · {row.query}</span>
          </p>
        ))}
      </Section>

      <Section title="Research Progress" note="有次数上限。夹具模式不调用远程模型。">
        <ul>
          {(view.runs || []).map((row) => (
            <li key={row.id}>
              {row.llm_mode || "fixture"} · {row.status} · {row.iterations ?? 0} 轮 · 模型调用 {row.llm_calls ?? 0}
              {row.error_code ? ` · ${row.error_code}` : ""}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Current Thesis">
        <p>{thesis.summary || "还没有 Thesis。"}</p>
        <p className="muted">多头：{thesis.bull_case || "—"}</p>
        <p className="muted">基准：{thesis.base_case || "—"}</p>
        <p className="muted">空头：{thesis.bear_case || "—"}</p>
        <p className="muted">失效：{thesis.invalidation || "—"}</p>
      </Section>

      <Section title="Key Claims" note="FACT 要有引文。ESTIMATE 是预测。INFERENCE 要有前提。">
        {CLAIM_ORDER.map((kind) => (
          <div key={kind}>
            <h3>{kind}</h3>
            <ul>
              {(claims[kind] || []).map((row) => (
                <li key={row.id}>
                  <span className="code">{row.id}</span> {row.claim_text}
                  <div className="muted">
                    {row.status} · {row.confidence}
                    {(row.evidence || []).map((item) => (
                      <span key={item.evidence_location}>
                        {" "}
                        · {item.evidence_location}
                        {item.source_title ? ` ${item.source_title}` : ""}
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </Section>

      <Section title="Conflicts">
        {(view.conflicts || []).length ? (
          <ul>
            {view.conflicts.map((row) => (
              <li key={`${row.metric}-${row.value_a}`}>
                {row.metric}：{row.value_a} 与 {row.value_b}。{row.possible_reason}（{row.status}）
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">没有并列的口径冲突。</p>
        )}
      </Section>

      <Section title="Value Chain">
        <ul>
          {(view.value_chain || []).map((node) => (
            <li key={node.node_name}>
              {node.node_name} · {node.role || "—"} · 瓶颈 {node.bottleneck || "UNKNOWN"}
              {node.upstream_node ? ` · 上游 ${node.upstream_node}` : ""}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Company Exposure" note="这是暴露矩阵，不是买入名单。">
        <table>
          <thead>
            <tr>
              <th>公司</th>
              <th>环节</th>
              <th>暴露</th>
              <th>收入</th>
              <th>证据水平</th>
            </tr>
          </thead>
          <tbody>
            {(view.company_mapping || []).map((row) => (
              <tr key={`${row.code}-${row.company}`}>
                <td>
                  {row.company} <span className="code">{row.code}</span>
                </td>
                <td>{row.value_chain_node}</td>
                <td>
                  {row.exposure_type}
                  {row.commercial_stage ? ` · ${row.commercial_stage}` : ""}
                </td>
                <td>{row.revenue_exposure || "UNKNOWN"}</td>
                <td>{row.evidence_level}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      {view.project.map?.company_view ? (
        <Section title="Company Thesis" note="商业模式、驱动、预期和失效条件。不写目标价。">
          <p>{view.project.map.company_view.revenue_driver_tree}</p>
          <p className="muted">行业位置 {view.project.map.company_view.industry_context || "UNKNOWN"}</p>
          <p className="muted">
            预期差 {view.project.map.company_view.variant?.status || "UNKNOWN"} · 一致预期{" "}
            {view.project.map.company_view.expectations?.consensus_view || "UNKNOWN"}
          </p>
          <p className="muted">
            暴露 {view.project.map.company_view.exposure_type} · 阶段 {view.project.map.company_view.commercial_stage}
          </p>
          <ul>
            {(view.project.map.company_view.monitoring || []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section title="Catalysts">
        <ul>
          {(thesis.catalysts || []).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </Section>

      <Section title="Risks">
        <ul>
          {(thesis.risks || []).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </Section>

      <Section title="Open Questions">
        <ul>
          {(view.open_questions || []).map((row) => (
            <li key={row.question}>{row.question}</li>
          ))}
        </ul>
      </Section>

      <Section title="Activity" note="执行轨迹。不展示隐藏推理。">
        {activity.length ? (
          <ul>
            {activity.map((row) => (
              <li key={row.id}>
                {row.status === "gap" ? "! " : "✓ "}
                {row.summary}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">这个项目还没有跨技能活动。</p>
        )}
      </Section>

      <Section title="Version History">
        <ul>
          {(view.thesis_versions || []).map((row) => (
            <li key={row.version}>
              v{row.version} · {row.as_of} · {row.diff_verdict || "初版"} · {row.created_at}
            </li>
          ))}
        </ul>
      </Section>
    </>
  );
}

async function projectActivity(id: string) {
  try {
    const response = await fetch(
      `${API_BASE}/api/agent/activity?project_id=${encodeURIComponent(id)}`,
      { cache: "no-store" },
    );
    if (!response.ok) return [];
    const data = await response.json();
    return (data.activities || []) as { id: string; status: string; summary: string }[];
  } catch {
    return [];
  }
}

export default async function ResearchProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return ResearchBoard({ id });
}
