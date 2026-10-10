import Link from "next/link";
import { api, type ChainBrief, type ChainLayer } from "@/lib/api";
import {
  Banner,
  ErrorState,
  Section,
  moveClass,
  num,
  pct,
} from "@/components/primitives";

export const dynamic = "force-dynamic";

function LayerBlock({ layer, active }: { layer: ChainLayer; active: boolean }) {
  return (
    <div className={`layer ${active ? "active" : ""}`}>
      <div className="layer-head">
        <div>
          <div className="kicker">{layer.side}</div>
          <div className="title">
            {layer.name}
            {active ? <span className="money-tag">今日资金</span> : null}
          </div>
          <div className="muted">{layer.logic}</div>
        </div>
        <div className={`layer-avg ${moveClass(layer.avg_pct)}`}>
          {pct(layer.avg_pct)}
          <div className="muted">
            {layer.quoted} 只有行情
            {layer.breadth != null ? ` · 上涨 ${(layer.breadth * 100).toFixed(0)}%` : ""}
          </div>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>标的</th>
            <th>角色</th>
            <th className="num">收盘</th>
            <th className="num">涨跌幅</th>
            <th>账本</th>
          </tr>
        </thead>
        <tbody>
          {layer.members.map((row) => (
            <tr key={row.code}>
              <td>
                {row.name} <span className="code">{row.code}</span>
              </td>
              <td className="muted">{row.role || "—"}</td>
              <td className="num">{num(row.close)}</td>
              <td className={`num ${moveClass(row.pct_chg)}`}>{pct(row.pct_chg)}</td>
              <td>{row.in_book ? "持仓" : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function ChainPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let data: ChainBrief;
  try {
    data = await api.chain(id);
  } catch (error) {
    return <ErrorState message={(error as Error).message} />;
  }

  const span = Math.max(
    1,
    ...data.layers.map((layer) => Math.abs(layer.avg_pct ?? 0)),
  );

  return (
    <>
      <p className="section-note">
        <Link href="/chains" style={{ color: "var(--accent)" }}>
          ← 全部产业链
        </Link>
      </p>

      <Section title={data.name} note={`${data.thesis} 行情截至 ${data.asof}。`}>
        {data.book.stale_warning ? (
          <Banner title="持仓快照已过期">
            账本日期 {data.book.asof}，距今 {data.book.stale_days} 天。数量可能已变，但「在不在这条链上」的判断仍可用。
          </Banner>
        ) : null}

        <div className="money-box">
          <div className="kicker">今日资金位置（池内相对强弱，非北向真值）</div>
          <div className="money-main">
            {data.money.name || "无"}
            <span className={moveClass(data.money.avg_pct)}>
              {pct(data.money.avg_pct)}
            </span>
          </div>
          <div className="muted">{data.money.why}</div>
          {data.switched ? (
            <div className="switch">
              相对 {data.prev_asof}，从 {data.prev_money?.name || "—"} 切到 {data.money.name}。
            </div>
          ) : null}
        </div>
      </Section>

      {data.overseas.length > 0 ? (
        <Section title="海外需求锚" note="美股定叙事。A 股多数时候只映射不定价。">
          <table>
            <thead>
              <tr>
                <th>标的</th>
                <th className="num">收盘</th>
                <th className="num">涨跌幅</th>
                <th>日期</th>
              </tr>
            </thead>
            <tbody>
              {data.overseas.map((row) => (
                <tr key={row.symbol}>
                  <td>
                    {row.name} <span className="code">{row.symbol}</span>
                  </td>
                  <td className="num">{num(row.close)}</td>
                  <td className={`num ${moveClass(row.pct_chg)}`}>{pct(row.pct_chg)}</td>
                  <td className="muted">{row.date}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}

      <Section title="层级强弱" note="等权平均涨跌幅。标签后为成分数量。">
        {data.layers.map((layer) => {
          const value = layer.avg_pct ?? 0;
          const width = (Math.abs(value) / span) * 50;
          return (
            <div className="barrow" key={layer.id}>
              <div className="label">
                {layer.name}
                {layer.id === data.money.layer ? " · 资金" : ""}
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
      </Section>

      <Section title="上中下游拆解" note="逻辑写在 chains.yaml，涨跌来自行情库。持仓列来自最新快照。">
        {data.layers.map((layer) => (
          <LayerBlock
            key={layer.id}
            layer={layer}
            active={layer.id === data.money.layer}
          />
        ))}
      </Section>

      <Section title="会不会打到账本" note={data.book.verdict}>
        {data.book.in_chain.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>链上持仓</th>
                <th className="num">现价</th>
                <th className="num">浮盈亏</th>
              </tr>
            </thead>
            <tbody>
              {data.book.in_chain.map((row) => (
                <tr key={row.code}>
                  <td>
                    {row.name} <span className="code">{row.code}</span>
                  </td>
                  <td className="num">{num(row.current_price)}</td>
                  <td className={`num ${moveClass(row.current_pnl_pct)}`}>
                    {pct(row.current_pnl_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">这条链上没有当前持仓。</p>
        )}
        {data.book.orphans.length > 0 ? (
          <p className="section-note" style={{ marginTop: 12 }}>
            账本孤儿（持有但没有研究框架）：
            {data.book.orphans.map((row) => `${row.name} ${row.code}`).join("、")}
          </p>
        ) : null}
        {data.book.in_universe_other_chain.length > 0 ? (
          <p className="section-note">
            持仓在其他链：
            {data.book.in_universe_other_chain.map((row) => row.name).join("、")}
          </p>
        ) : null}
      </Section>

      {data.news.length > 0 ? (
        <Section title="落入本链的新闻" note="只显示标题命中本链关键词的条目，不是全市场相关新闻。">
          <div className="newslist">
            {data.news.map((item) => (
              <div className="newsitem" key={`${item.published_at}-${item.title}`}>
                <div className="head">
                  <span>{item.source}</span>
                  <span>{item.published_at.slice(0, 16)}</span>
                  <span>{item.matched.join(" / ")}</span>
                </div>
                <div className="title">{item.title}</div>
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      <p className="section-note">{data.disclaimer}</p>
    </>
  );
}
