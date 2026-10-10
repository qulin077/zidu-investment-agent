import Link from "next/link";
import { api, type Board, type Mover, type NewsItem } from "@/lib/api";
import {
  Banner,
  ErrorState,
  Section,
  moveClass,
  num,
  pct,
} from "@/components/primitives";
import { ResearchUpdateInbox } from "@/components/ResearchUpdateInbox";

export const dynamic = "force-dynamic";

function HealthStrip({ health }: { health: Board["health"] }) {
  return (
    <div className="health">
      {health.datasets.map((item) => (
        <div key={item.name} className={`chip ${item.ok ? "ok" : "stale"}`}>
          <div className="name">{item.description}</div>
          <div className="value">{item.rows.toLocaleString("zh-CN")}</div>
          <div className="meta">
            {item.asof ? `最新 ${item.asof.slice(0, 10)}` : "无日期维度"}
            {item.coverage !== null
              ? ` · 覆盖 ${(item.coverage * 100).toFixed(0)}%`
              : ""}
          </div>
          {item.issues.length > 0 ? (
            <div className="issue">{item.issues.join("；")}</div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function Spark({ series }: { series: number[] }) {
  if (series.length < 2) return null;
  const min = Math.min(...series);
  const max = Math.max(...series);
  const span = Math.max(0.01, max - min);
  return (
    <div className="spark" aria-hidden>
      {series.map((value, index) => (
        <span
          key={index}
          style={{ height: `${8 + ((value - min) / span) * 22}px` }}
        />
      ))}
    </div>
  );
}

function MoverTable({ rows }: { rows: Mover[] }) {
  return (
    <table>
      <thead>
        <tr>
          <th>标的</th>
          <th>板块</th>
          <th className="num">收盘</th>
          <th className="num">涨跌幅</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.code}>
            <td>
              {row.name} <span className="code">{row.code}</span>
            </td>
            <td className="muted">{row.sector || "—"}</td>
            <td className="num">{num(row.close)}</td>
            <td className={`num ${moveClass(row.pct_chg)}`}>{pct(row.pct_chg)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SectorBars({ sectors }: { sectors: Board["sectors"]["sectors"] }) {
  const span = Math.max(1, ...sectors.map((s) => Math.abs(s.avg_pct ?? 0)));
  return (
    <div>
      {sectors.map((item) => {
        const value = item.avg_pct ?? 0;
        const width = (Math.abs(value) / span) * 50;
        return (
          <div className="barrow" key={item.sector}>
            <div className="label" title={item.sector}>
              {item.sector}
              <span className="muted"> · {item.count}</span>
            </div>
            <div className="bartrack">
              <div
                className="barfill"
                style={{
                  left: value >= 0 ? "50%" : `${50 - width}%`,
                  width: `${width}%`,
                  background: value >= 0 ? "var(--up)" : "var(--down)",
                }}
              />
            </div>
            <div className={`val ${moveClass(value)}`}>{pct(value)}</div>
          </div>
        );
      })}
    </div>
  );
}

function NewsList({ rows }: { rows: NewsItem[] }) {
  return (
    <div className="newslist">
      {rows.map((item) => {
        const inner = (
          <>
            <div className="head">
              <span>{item.source}</span>
              <span>{(item.published_at || "").slice(0, 16)}</span>
            </div>
            <div className="title">{item.title}</div>
            {item.summary ? <div className="summary">{item.summary}</div> : null}
          </>
        );
        if (item.url) {
          return (
            <a
              className="newsitem"
              key={item.id}
              href={item.url}
              target="_blank"
              rel="noreferrer"
            >
              {inner}
            </a>
          );
        }
        return (
          <div className="newsitem" key={item.id}>
            {inner}
          </div>
        );
      })}
    </div>
  );
}

export default async function BoardPage() {
  let data: Board;
  try {
    data = await api.board();
  } catch (error) {
    return <ErrorState message={(error as Error).message} />;
  }

  const { health, pulse, movers, sectors, positions, account, news, research_updates } = data;
  const { indices, vix, emotion, themes, breadth, macro } = pulse;
  const mid = Math.ceil(news.rows.length / 2);
  const newsLeft = news.rows.slice(0, mid);
  const newsRight = news.rows.slice(mid);
  const accountTail = account.rows.slice(-8);

  return (
    <>
      {!health.ok ? (
        <Banner title="部分数据集已过期">
          过期的数据集在下方以黄色左边框标出。行情可用{" "}
          <code>python3 -m core.ingest.runner refresh</code> 刷新。
        </Banner>
      ) : null}

      <Banner title="看板看环境，也发现变化">
        指数、VIX、情绪和新闻在这里汇总；重大变化先进入 Research 收件箱，不在看板直接下结论。今天要处理的交易与复盘事项请到{" "}
        <Link href="/today" style={{ color: "var(--accent)" }}>
          Today
        </Link>
        。
      </Banner>

      <Section
        title="市场脉冲"
        note="A 股指数走新浪实时；VIX 是 CBOE 恐慌指数（Yahoo ^VIX，失败则退回日更宏观快照）。"
      >
        <div className="pulse-idx">
          {indices.map((item) => (
            <div className="pulse-card" key={item.code}>
              <div className="kicker">{item.name}</div>
              <div className="pulse-close">{num(item.close, 2)}</div>
              <div className={`pulse-chg ${moveClass(item.pct_chg)}`}>
                {pct(item.pct_chg)}
              </div>
            </div>
          ))}
        </div>

        <div className="pulse-grid">
          <div className="pulse-card vix">
            <div className="kicker">{vix.name}</div>
            <div className="pulse-close">{vix.value == null ? "—" : num(vix.value, 2)}</div>
            <div className={`pulse-chg ${moveClass(vix.chg_1d_pct)}`}>
              {pct(vix.chg_1d_pct)} · {vix.band}
            </div>
            <Spark series={vix.series || []} />
            <div className="meta">
              {vix.date || "—"} · {vix.source}。&lt;15 偏低偏贪婪，15–20 正常，20–30 升温，&gt;30 恐慌。
            </div>
          </div>
          <div className="pulse-card">
            <div className="kicker">A股情绪 · {emotion.asof || "—"}</div>
            <div className="pulse-close">{emotion.stage || "—"}</div>
            <div className="meta">{emotion.why || "—"}</div>
            <div className="statrow">
              <span>涨停 {emotion.limit_up ?? "—"}</span>
              <span>炸板 {emotion.zhaban ?? "—"}</span>
              <span>高度 {emotion.height ?? "—"}</span>
              <span>炸板率 {emotion.zhaban_rate == null ? "—" : `${emotion.zhaban_rate}%`}</span>
            </div>
            <div className="meta">{emotion.action || ""}</div>
          </div>
          <div className="pulse-card">
            <div className="kicker">池内涨跌 · {breadth.asof || "—"}</div>
            <div className="pulse-close">
              {breadth.n ? `${breadth.up}/${breadth.n}` : "—"}
            </div>
            <div className="meta">
              上涨 {breadth.up} · 下跌 {breadth.down} · 平 {breadth.flat}
            </div>
          </div>
        </div>
      </Section>

      {themes.themes.length ? (
        <Section
          title="涨停主题"
          note={`截至 ${themes.asof}，按连板驱动题材。看梯队，不看首板故事。`}
        >
          <div className="theme-grid">
            {themes.themes.map((item) => (
              <div className="theme-card" key={item.theme}>
                <div className="name">
                  {item.theme}
                  <span className="muted">
                    {" "}
                    {item.n} 家 · 高度 {item.max_board}
                  </span>
                </div>
                <div className="meta">{item.role}</div>
                <div className="meta">{item.names}</div>
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {macro.items.length ? (
        <Section title="宏观快照" note={`asof ${macro.asof || "—"}。日更落盘，不是实时。`}>
          <div className="macro-strip">
            {macro.items.map((item) => (
              <div className="macro-cell" key={item.id}>
                <div className="kicker">{item.name}</div>
                <div className="val">
                  {item.value == null ? "—" : num(item.value, item.value >= 100 ? 0 : 2)}
                  {item.unit ? ` ${item.unit}` : ""}
                </div>
                <div className={`meta ${moveClass(item.chg_1d_pct)}`}>
                  {item.chg_1d_pct == null ? item.date || "" : pct(item.chg_1d_pct)}
                </div>
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      <Section
        title="研究更新收件箱"
        note="每日新闻先匹配你已经跟踪的公司、行业和事件；由你决定是否启动核验，不自动污染长期档案。"
      >
        <ResearchUpdateInbox
          initialRows={research_updates.rows}
          initialCount={research_updates.pending_count}
        />
      </Section>

      <Section
        title="新闻"
        note={`展示 ${news.rows.length} 条，按来源抽样后倒序。库内共 ${news.sources.reduce((n, s) => n + s.count, 0)} 条。`}
      >
        <div className="tagrow">
          {news.sources.slice(0, 10).map((item) => (
            <span className="tag" key={item.source}>
              {item.source} {item.count}
            </span>
          ))}
        </div>
        <div className="cols">
          <NewsList rows={newsLeft} />
          <NewsList rows={newsRight} />
        </div>
      </Section>

      <Section
        title="池内异动"
        note={`截至 ${movers.asof}，按当日涨跌幅排序。涨红跌绿。`}
      >
        <div className="cols">
          <div>
            <p className="section-note">领涨</p>
            <MoverTable rows={movers.gainers} />
          </div>
          <div>
            <p className="section-note">领跌</p>
            <MoverTable rows={movers.losers} />
          </div>
        </div>
      </Section>

      <Section
        title="板块波动"
        note={`截至 ${sectors.asof}，按 universe.yaml 的 sector 聚合当日平均涨跌幅。`}
      >
        <SectorBars sectors={sectors.sectors} />
      </Section>

      <Section
        title="持仓"
        note={`快照日 ${positions.asof}${
          positions.stale_days && positions.stale_days > 7
            ? `（距今 ${positions.stale_days} 天，已过期）`
            : ""
        }，现价取自 ${positions.quote_date} 行情。`}
      >
        {positions.stale_days !== null && positions.stale_days > 7 ? (
          <Banner title="持仓快照已过期">
            下方的持仓数量与成本来自 {positions.asof} 的快照，现价与浮盈亏按最新行情计算。
          </Banner>
        ) : null}
        <table>
          <thead>
            <tr>
              <th>标的</th>
              <th className="num">数量</th>
              <th className="num">成本</th>
              <th className="num">现价</th>
              <th className="num">市值</th>
              <th className="num">浮盈亏</th>
            </tr>
          </thead>
          <tbody>
            {positions.rows.map((row) => (
              <tr key={row.code}>
                <td>
                  {row.name} <span className="code">{row.code}</span>
                </td>
                <td className="num">{num(row.qty, 0)}</td>
                <td className="num">{num(row.cost)}</td>
                <td className="num">{num(row.current_price)}</td>
                <td className="num">{num(row.current_value, 0)}</td>
                <td className={`num ${moveClass(row.current_pnl_pct)}`}>
                  {pct(row.current_pnl_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      {accountTail.length ? (
        <Section title="账户曲线" note={`最近 ${accountTail.length} 个快照，截至 ${account.asof}。`}>
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th className="num">权益</th>
                <th className="num">当日</th>
                <th className="num">仓位</th>
              </tr>
            </thead>
            <tbody>
              {accountTail.map((row) => (
                <tr key={row.date}>
                  <td className="muted">{row.date}</td>
                  <td className="num">{num(row.equity, 0)}</td>
                  <td className={`num ${moveClass(row.pnl_day_pct)}`}>
                    {pct(row.pnl_day_pct)}
                  </td>
                  <td className="num">
                    {row.position_pct == null ? "—" : `${row.position_pct.toFixed(0)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}

      <Section
        title="数据状态"
        note={`契约校验于 ${health.checked_at}。不达标即标记，不静默使用。`}
      >
        <HealthStrip health={health} />
      </Section>
    </>
  );
}
