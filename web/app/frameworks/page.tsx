import Link from "next/link";
import { api, type FrameworkDoc } from "@/lib/api";
import { ErrorState, Section } from "@/components/primitives";

export const dynamic = "force-dynamic";

export default async function FrameworksPage({
  searchParams,
}: {
  searchParams: Promise<{ path?: string; section?: string }>;
}) {
  const { path, section } = await searchParams;

  let docs: FrameworkDoc[];
  try {
    docs = (await api.frameworks()).rows;
  } catch (error) {
    return <ErrorState message={(error as Error).message} />;
  }

  const sections = Array.from(new Set(docs.map((d) => d.section)));
  const visible = section ? docs.filter((d) => d.section === section) : docs;

  let content: { title: string; content: string } | null = null;
  if (path) {
    try {
      content = await api.frameworkContent(path);
    } catch (error) {
      content = { title: "读取失败", content: (error as Error).message };
    }
  }

  if (content) {
    return (
      <Section title={content.title} note={path}>
        <p className="section-note">
          <Link href="/frameworks" style={{ color: "var(--accent)" }}>
            ← 返回文档列表
          </Link>
        </p>
        <div className="docbody">{content.content}</div>
      </Section>
    );
  }

  return (
    <Section
      title="研究框架"
      note={`${docs.length} 篇框架与方法论文档，来自仓库内的研究目录。`}
    >
      <div className="tagrow">
        <Link href="/frameworks" className={`tag ${!section ? "active" : ""}`}>
          全部
        </Link>
        {sections.map((item) => (
          <Link
            key={item}
            href={`/frameworks?section=${encodeURIComponent(item)}`}
            className={`tag ${section === item ? "active" : ""}`}
          >
            {item}
          </Link>
        ))}
      </div>

      <div className="doclist">
        {visible.map((doc) => (
          <Link
            className="docitem"
            key={doc.path}
            href={`/frameworks?path=${encodeURIComponent(doc.path)}`}
          >
            <span className="section">{doc.section}</span>
            <span>{doc.title}</span>
            <span className="spacer" style={{ marginLeft: "auto" }} />
            <span className="code">{(doc.size / 1024).toFixed(1)} KB</span>
          </Link>
        ))}
      </div>
    </Section>
  );
}
