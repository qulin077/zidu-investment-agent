import Link from "next/link";
import { api } from "@/lib/api";
import { ErrorState, Section } from "@/components/primitives";

export const dynamic = "force-dynamic";

export default async function ChainsIndexPage() {
  let rows;
  try {
    rows = (await api.chains()).rows;
  } catch (error) {
    return <ErrorState message={(error as Error).message} />;
  }

  return (
    <Section
      title="产业链看板"
      note="每条链是你自己画的上中下游，不是交易所行业分类。点进去看今日资金落在哪一层、会不会打到当前持仓。"
    >
      <div className="chain-grid">
        {rows.map((row) => (
          <Link className="chain-card" href={`/chains/${row.id}`} key={row.id}>
            <div className="kicker">{row.id}</div>
            <div className="title">{row.name}</div>
            <div className="muted">{row.thesis}</div>
            <div className="meta">
              {row.n_members} 只 · {row.layers.length} 层
            </div>
          </Link>
        ))}
      </div>
    </Section>
  );
}
