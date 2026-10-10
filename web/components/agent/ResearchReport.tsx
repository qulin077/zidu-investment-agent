"use client";

import { ReactNode } from "react";

type ReportSection = {
  title: string;
  lines: string[];
};

const INTAKE_OPTIONS = [
  "公司基本盘与竞争壁垒",
  "最近财报和事实变化",
  "增长变量与利润弹性",
  "市场预期、估值与预期差",
  "风险与失效条件",
  "完整公司档案",
];

function inlineContent(value: string) {
  const nodes: ReactNode[] = [];
  const pattern = /\[([^\]]+)\]\((https?:\/\/[^)]+)\)|\*\*([^*]+)\*\*|`([^`]+)`/g;
  let offset = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(value)) !== null) {
    if (match.index > offset) nodes.push(value.slice(offset, match.index));
    if (match[1] && match[2]) {
      nodes.push(
        <a key={`${match.index}-${match[2]}`} href={match[2]} target="_blank" rel="noreferrer">
          {match[1]}
          <span aria-hidden="true"> ↗</span>
        </a>,
      );
    } else if (match[3]) {
      nodes.push(<strong key={`strong-${match.index}`}>{match[3]}</strong>);
    } else if (match[4]) {
      nodes.push(<code key={`code-${match.index}`}>{match[4]}</code>);
    }
    offset = match.index + match[0].length;
  }
  if (offset < value.length) nodes.push(value.slice(offset));
  return nodes;
}

function parseReport(content: string) {
  const lines = content.split("\n").map((line) => line.trim());
  const titleIndex = lines.findIndex((line) => line.startsWith("# "));
  if (titleIndex < 0) return null;
  const title = lines[titleIndex].slice(2).trim();
  const preface = lines.slice(0, titleIndex).filter(Boolean);
  const meta: string[] = [];
  const sections: ReportSection[] = [];
  let current: ReportSection | null = null;

  for (const line of lines.slice(titleIndex + 1)) {
    if (!line) continue;
    if (line.startsWith("## ")) {
      current = { title: line.slice(3).trim(), lines: [] };
      sections.push(current);
      continue;
    }
    if (current) current.lines.push(line);
    else meta.push(line);
  }
  return { title, preface, meta, sections };
}

function sectionTone(title: string) {
  if (title.includes("跨来源综合分析")) return "analyst";
  if (title.includes("证据覆盖") || title.includes("证据缺口")) return "gap";
  if (title.includes("财报")) return "financial";
  if (title.includes("风险") || title.includes("失效")) return "risk";
  if (title.includes("变化")) return "change";
  if (title.includes("判断")) return "thesis";
  if (title.includes("预期") || title.includes("股价")) return "expectation";
  if (title.includes("来源")) return "sources";
  if (title.includes("监控")) return "monitoring";
  if (title.includes("时间线") || title.includes("主体") || title.includes("技术")) return "structure";
  if (title.includes("产业") || title.includes("传导") || title.includes("经济变量")) return "impact";
  return "default";
}

function sectionWide(title: string) {
  return ["一句话判断", "跨来源综合分析", "本轮变化", "产业与板块影响", "证据覆盖", "来源"].some((token) => title.includes(token));
}

function renderSectionLines(lines: string[]) {
  const result: ReactNode[] = [];
  let bullets: string[] = [];
  let tableLines: string[] = [];

  const flushBullets = () => {
    if (!bullets.length) return;
    const group = bullets;
    bullets = [];
    result.push(
      <ul key={`list-${result.length}`}>
        {group.map((line, index) => (
          <li className={line.includes("UNKNOWN") ? "is-unknown" : ""} key={`${line}-${index}`}>
            {inlineContent(line)}
          </li>
        ))}
      </ul>,
    );
  };

  const flushTable = () => {
    if (!tableLines.length) return;
    const raw = tableLines;
    tableLines = [];
    const rows = raw.map((line) => line.replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim()));
    const divider = rows[1] || [];
    const valid = rows.length >= 2 && divider.length === rows[0].length && divider.every((cell) => /^:?-{3,}:?$/.test(cell));
    if (!valid) {
      raw.forEach((line, index) => result.push(<p key={`raw-table-${result.length}-${index}`}>{inlineContent(line)}</p>));
      return;
    }
    const headers = rows[0];
    const body = rows.slice(2);
    result.push(
      <div className="agent-report-table-wrap" key={`table-${result.length}`}>
        <table>
          <thead>
            <tr>
              {headers.map((cell, index) => (
                <th className={divider[index]?.endsWith(":") ? "is-number" : ""} key={`${cell}-${index}`}>
                  {inlineContent(cell)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((row, rowIndex) => (
              <tr key={`row-${rowIndex}`}>
                {headers.map((_, cellIndex) => (
                  <td
                    className={`${divider[cellIndex]?.endsWith(":") ? "is-number" : ""} ${(row[cellIndex] || "").includes("UNKNOWN") || row[cellIndex] === "—" ? "is-unknown" : ""}`.trim()}
                    key={`cell-${rowIndex}-${cellIndex}`}
                  >
                    {inlineContent(row[cellIndex] || "—")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>,
    );
  };

  lines.forEach((line, index) => {
    if (line.startsWith("|") && line.endsWith("|")) {
      flushBullets();
      tableLines.push(line);
      return;
    }
    flushTable();
    if (line.startsWith("- ")) {
      bullets.push(line.slice(2));
      return;
    }
    flushBullets();
    if (line.startsWith("### ")) {
      result.push(<h4 key={`heading-${index}`}>{inlineContent(line.slice(4))}</h4>);
      return;
    }
    result.push(
      <p className={line.includes("UNKNOWN") ? "is-unknown" : ""} key={`paragraph-${index}`}>
        {inlineContent(line)}
      </p>,
    );
  });
  flushTable();
  flushBullets();
  return result;
}

export function isCompanyReport(content: string) {
  return /(^|\n)#\s*公司档案(?:\n|$)/.test(content);
}

export function isStructuredResearchReport(content: string) {
  return /(^|\n)#\s*(?:公司档案|行业跟踪档案|事件跟踪档案|主题跟踪档案)(?:\n|$)/.test(content);
}

export function ResearchReport({
  content,
  companyName,
  subjectName,
  kind = "company",
}: {
  content: string;
  companyName?: string;
  subjectName?: string;
  kind?: "company" | "industry" | "event";
}) {
  const report = parseReport(content);
  if (!report) return null;
  const displayTitle = subjectName || companyName || report.title;
  const kicker = kind === "industry" ? "Industry tracking" : kind === "event" ? "Event impact" : "Company research";
  const coverageMatch = content.match(/已完成\s*(\d+)\/(\d+)\s*项必需检查/);
  const covered = Number(coverageMatch?.[1] || 0);
  const required = Number(coverageMatch?.[2] || 0);
  const coveragePct = required ? Math.round((covered / required) * 100) : 0;
  const gapSection = report.sections.find((section) => section.title.includes("证据覆盖") || section.title.includes("证据缺口"));
  const gapCount = gapSection?.lines.filter((line) => line.startsWith("|") && !/^\|\s*(?:---|待补模块)/.test(line)).length || 0;

  return (
    <article className="agent-research-report">
      <header className="agent-report-hero">
        <div>
          <span className="agent-report-kicker">{kicker}</span>
          <h2>{displayTitle}</h2>
        </div>
        <div className="agent-report-status">
          <span className="status-dot" />
          持续更新
        </div>
      </header>
      {report.preface.length ? (
        <div className="agent-report-preface">{report.preface.map((line) => <p key={line}>{inlineContent(line)}</p>)}</div>
      ) : null}
      {report.meta.length ? (
        <div className="agent-report-meta">
          {report.meta.join(" · ").split(" · ").filter(Boolean).map((item) => <span key={item}>{item}</span>)}
        </div>
      ) : null}
      {required ? (
        <section className="agent-report-coverage" aria-label="研究覆盖率">
          <div className="agent-report-coverage-score">
            <strong>{covered}<span>/{required}</span></strong>
            <small>必需研究检查</small>
          </div>
          <div className="agent-report-coverage-progress">
            <div><span>检查执行覆盖</span><b>{coveragePct}%</b></div>
            <progress max={required} value={covered} />
            <small>{gapCount || Math.max(required - covered, 0)} 项执行缺口已按搜索、读取和抽取阶段分别诊断；内容是否充分见右侧待回答</small>
          </div>
        </section>
      ) : null}
      {content.includes("待核对") || content.includes("UNKNOWN") ? (
        <div className="agent-report-unknown-note">
          <strong>缺口不再等于一句“没找到”</strong>
          <span>报告末尾会区分：没有搜索结果、候选正文打不开、正文已打开但没有抽出合格证据，以及尚未执行该分支。</span>
        </div>
      ) : null}
      <div className="agent-report-grid">
        {report.sections.map((section, index) => {
          const tone = sectionTone(section.title);
          return (
            <section className={`agent-report-card tone-${tone} ${sectionWide(section.title) ? "is-wide" : ""}`} key={`${section.title}-${index}`}>
              <div className="agent-report-card-head">
                <span className="agent-report-index">{String(index + 1).padStart(2, "0")}</span>
                <h3>{section.title}</h3>
              </div>
              <div className="agent-report-card-body">{renderSectionLines(section.lines)}</div>
            </section>
          );
        })}
      </div>
    </article>
  );
}

export function IntakeChoices({
  content,
  disabled,
  onChoose,
}: {
  content: string;
  disabled?: boolean;
  onChoose: (value: string) => void;
}) {
  if (!content.includes("更关心哪一块")) return null;
  return (
    <div className="agent-intake-options" aria-label="选择研究重点">
      {INTAKE_OPTIONS.map((option) => (
        <button type="button" disabled={disabled} onClick={() => onChoose(option)} key={option}>
          {option}
        </button>
      ))}
    </div>
  );
}

export { inlineContent };
