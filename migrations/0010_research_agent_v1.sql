-- 研究 Agent V1。0009 已经进过本地库，这里只加列。
-- 新库会先建 0009 再跑这些 ALTER；已有列会被迁移器跳过。

ALTER TABLE research_run ADD COLUMN llm_mode TEXT NOT NULL DEFAULT '';
ALTER TABLE research_run ADD COLUMN iterations INTEGER NOT NULL DEFAULT 0;
ALTER TABLE research_run ADD COLUMN input_tokens INTEGER;
ALTER TABLE research_run ADD COLUMN output_tokens INTEGER;
ALTER TABLE research_run ADD COLUMN estimated_cost REAL;
ALTER TABLE research_run ADD COLUMN question_id TEXT NOT NULL DEFAULT '';

ALTER TABLE research_claim ADD COLUMN run_id TEXT NOT NULL DEFAULT '';

ALTER TABLE research_conflict ADD COLUMN topic TEXT NOT NULL DEFAULT '';
ALTER TABLE research_conflict ADD COLUMN claim_ids TEXT NOT NULL DEFAULT '[]';

ALTER TABLE research_value_chain ADD COLUMN parent_node TEXT NOT NULL DEFAULT '';
ALTER TABLE research_value_chain ADD COLUMN evidence_refs TEXT NOT NULL DEFAULT '[]';

ALTER TABLE research_company_mapping ADD COLUMN revenue_evidence TEXT NOT NULL DEFAULT '';

ALTER TABLE research_thesis ADD COLUMN invalidation_json TEXT NOT NULL DEFAULT '[]';
