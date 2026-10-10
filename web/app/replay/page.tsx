import Link from "next/link";
import { api, type PersonaMode, type ReplayDay } from "@/lib/api";
import { ReplayChat } from "@/components/replay-chat";
import {
  Banner,
  ErrorState,
  Section,
  num,
} from "@/components/primitives";

export const dynamic = "force-dynamic";

export default async function ReplayPage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>;
}) {
  const { date } = await searchParams;
  let data: ReplayDay;
  try {
    data = await api.replay(date);
  } catch (error) {
    return <ErrorState message={(error as Error).message} />;
  }

  let personas: { modes: Record<string, PersonaMode> } | null = null;
  try {
    personas = await api.personas();
  } catch {
    personas = null;
  }

  const perceptionDebt = data.predictions.pending_count;
  const executionWarn = data.unplanned;

  return (
    <>
      <ReplayChat />

      <Section
        title="复盘"
        note="交易没有标准答案。这里只存两套账：你会不会读市场，你做没做到。同一页下面是模式透镜。"
      >
        <div className="tagrow">
          {data.dates.map((day) => (
            <Link
              key={day}
              href={`/replay?date=${day}`}
              className={`tag ${day === data.asof ? "active" : ""}`}
            >
              {day}
            </Link>
          ))}
        </div>

        <div className="ledger-grid">
          <div className="ledger">
            <div className="kicker">感知账 · 理解力</div>
            <div className="title">
              {perceptionDebt} 条预期待验
              <span className="muted"> / 已打分 {data.predictions.scored_count}</span>
            </div>
            <p className="muted">{data.purpose.perception}</p>
          </div>
          <div className="ledger">
            <div className="kicker">执行账 · 纪律</div>
            <div className="title">
              {executionWarn} 笔计划外
              <span className="muted">
                {" "}
                / 买入缺 E 类型 {data.missing_earning_type}
              </span>
            </div>
            <p className="muted">{data.purpose.execution}</p>
          </div>
        </div>
      </Section>

      {perceptionDebt > 0 ? (
        <Banner title="理解力欠账">
          预测台账里 {perceptionDebt} 条还停在「待验」。不打分的预期不能证明感知在进步，只是日记。
        </Banner>
      ) : null}

      <Section
        title={`${data.asof} 交割`}
        note="每笔必须能回答：为什么买/卖、主赚钱类型、失效条件。缺的就是执行债。"
      >
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>动作</th>
              <th>标的</th>
              <th className="num">价格</th>
              <th className="num">数量</th>
              <th>主 E</th>
              <th>逻辑</th>
              <th>计划内</th>
            </tr>
          </thead>
          <tbody>
            {data.trades.map((row) => (
              <tr key={row.id}>
                <td className="muted">{row.time}</td>
                <td className={row.side.includes("买") ? "up" : "down"}>
                  {row.side}
                </td>
                <td>
                  {row.name} <span className="code">{row.code}</span>
                </td>
                <td className="num">{num(row.price)}</td>
                <td className="num">{num(row.qty, 0)}</td>
                <td>{row.earning_type || "未填"}</td>
                <td>{row.reason || "—"}</td>
                <td className={row.planned.startsWith("否") ? "up" : "muted"}>
                  {row.planned || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section
        title="感知账：预期对账"
        note="窗口过了还待验 = 这套系统没有在迭代。对的要写为什么对，错的要写错因标签。"
      >
        <table>
          <thead>
            <tr>
              <th>写下日</th>
              <th>ID</th>
              <th>窗口止</th>
              <th>预测</th>
              <th>置信</th>
              <th>结果</th>
            </tr>
          </thead>
          <tbody>
            {data.predictions.pending.map((row) => (
              <tr key={`${row.日期}-${row.ID}`}>
                <td className="muted">{row.日期}</td>
                <td>{row.ID}</td>
                <td>{row.窗口止}</td>
                <td>{row.预测}</td>
                <td className="num">{row["置信1-5"]}</td>
                <td className="up">{row.结果 || "待验"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section
        title="采集质量（全样本）"
        note={`共 ${data.trade_total} 笔。机器能填的满，人要填的空——复盘产品要解决的就是这件事。`}
      >
        <div className="fill-grid">
          {Object.entries(data.fill_rates).map(([label, value]) => (
            <div className="fillcard" key={label}>
              <div
                className="pct"
                style={{
                  color: value >= 80 ? "var(--down)" : "var(--warn)",
                }}
              >
                {value.toFixed(1)}%
              </div>
              <div className="label">{label}</div>
            </div>
          ))}
        </div>
      </Section>

      {personas ? (
        <div id="modes">
          <Section
            title="模式"
            note="不是独立房间。同一组交割，换一副眼镜：必看什么、禁止看什么、何时失效。"
          >
            <div className="persona-grid">
              {Object.entries(personas.modes).map(([id, mode]) => (
                <div className="persona" key={id}>
                  <div className="name">
                    {mode.name}
                    <span className="id">{id}</span>
                  </div>
                  <p>{mode.one_liner}</p>
                  <div className="meta">看：{(mode.watches || []).slice(0, 3).join("、")}</div>
                  <div className="meta">不看：{(mode.ignores || []).slice(0, 2).join("、")}</div>
                  <div className="meta">失效：{mode.fail_when}</div>
                  <div className="meta">
                    {mode.position} · {(mode.earning_types || []).join("/")}
                  </div>
                </div>
              ))}
            </div>
          </Section>
        </div>
      ) : null}
    </>
  );
}
