import Link from "next/link";
import { api } from "@/lib/api";
import { Banner, ErrorState, Section } from "@/components/primitives";

export const dynamic = "force-dynamic";

export default async function NewResearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; theme?: string; run?: string; skill?: string }>;
}) {
  const { q = "", theme = "", run = "", skill = "" } = await searchParams;
  const question = q.trim();
  let planError = "";
  let plan = null;
  let routed = "";
  let reason = "";
  if (question) {
    try {
      const response = await api.researchPlan(question, theme, skill);
      if (!response.ok) planError = response.error_message || response.error_code || "计划没有生成";
      else {
        plan = response.plan || null;
        routed = response.skill || response.route?.skill || "";
        reason = response.route?.reason_code || "";
      }
    } catch (err) {
      planError = (err as Error).message;
    }
  }

  let runError = "";
  let created: { ok?: boolean; project_id?: string; thesis_version?: number; error_message?: string; status?: string } | null = null;
  if (question && (run === "fixture" || run === "remote")) {
    try {
      created = await api.researchCreate({
        research_question: question,
        industry_or_theme: theme,
        mode: run,
        market_scope: ["A股", "美股"],
      });
      if (!created.ok) runError = created.error_message || created.status || "没有写入 Thesis";
    } catch (err) {
      runError = (err as Error).message;
    }
  }

  const query = new URLSearchParams({ q: question, theme });
  return (
    <>
      <Section title="新研究" note="先看计划，再跑。跑完进的是底稿，不是推荐名单。">
        <form className="research-form" action="/research/new" method="get">
          <input
            name="q"
            defaultValue={question}
            placeholder="Rubin放量后AI电源产业链怎么传导？"
            aria-label="研究问题"
          />
          <input name="theme" defaultValue={theme} placeholder="行业或主题，例如 AI电源" aria-label="主题" />
          <label>
            Skill
            <select name="skill" defaultValue={skill} aria-label="研究技能">
              <option value="">自动</option>
              <option value="industry-research">industry-research</option>
              <option value="company-research">company-research</option>
            </select>
          </label>
          <button type="submit">生成研究计划</button>
        </form>
        <p className="section-note">
          <Link href="/research/projects">已有项目</Link>
        </p>
      </Section>

      {planError ? <ErrorState message={planError} /> : null}
      {plan ? (
        <Section title="Research Plan" note={`${routed || "未路由"} · ${reason}`}>
          {(plan.tasks || []).length ? (
            <ol>
              {(plan.tasks || []).map((task) => (
                <li key={task.id}>
                  <strong>
                    {task.id} · {task.category}
                  </strong>
                  <div className="muted">{task.question}</div>
                </li>
              ))}
            </ol>
          ) : null}
          <p>
            <Link href={`/research/new?${query.toString()}&run=fixture`}>用夹具跑完整研究循环</Link>
          </p>
          <p className="muted">远程对照不从这里直接打模型，也不写成正式 Thesis。</p>
        </Section>
      ) : null}

      {runError ? (
        <Banner title="这轮没有写成正式 Thesis">
          {runError}
        </Banner>
      ) : null}
      {created?.ok && created.project_id ? (
        <Banner title={`Thesis v${created.thesis_version || 1} 已写入`}>
          <Link href={`/research/${created.project_id}`}>打开研究项目</Link>
        </Banner>
      ) : null}
    </>
  );
}
