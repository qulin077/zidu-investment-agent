import Link from "next/link";
import { api, type Board } from "@/lib/api";
import { ErrorState, Section } from "@/components/primitives";

export const dynamic = "force-dynamic";

export default async function NewsPage({
  searchParams,
}: {
  searchParams: Promise<{ source?: string }>;
}) {
  const { source } = await searchParams;

  let data: Board["news"];
  try {
    data = await api.news(120, source);
  } catch (error) {
    return <ErrorState message={(error as Error).message} />;
  }

  return (
    <Section
      title="新闻与叙事"
      note="金十快讯、政策要闻与叙事文章的统一收件箱。点标题跳原文。"
    >
      <div className="tagrow">
        <Link href="/news" className={`tag ${!source ? "active" : ""}`}>
          全部
        </Link>
        {data.sources.map((item) => (
          <Link
            key={item.source}
            href={`/news?source=${encodeURIComponent(item.source)}`}
            className={`tag ${source === item.source ? "active" : ""}`}
          >
            {item.source} · {item.count}
          </Link>
        ))}
      </div>

      <div className="newslist">
        {data.rows.map((item) => (
          <a
            className="newsitem"
            key={item.id}
            href={item.url || undefined}
            target="_blank"
            rel="noreferrer"
          >
            <div className="head">
              <span>{item.source}</span>
              <span>{item.published_at.slice(0, 16)}</span>
              {item.tags ? <span>{item.tags}</span> : null}
            </div>
            <div className="title">{item.title}</div>
            {item.summary ? <div className="summary">{item.summary}</div> : null}
          </a>
        ))}
      </div>
    </Section>
  );
}
