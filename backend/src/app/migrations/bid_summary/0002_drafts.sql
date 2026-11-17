-- Working state: shared drafts with a version for conflict detection, and who
-- has one open. A draft is retired when its revision is submitted.
CREATE TABLE bid_draft (
    draft_id VARCHAR, bid_id VARCHAR, deal_id VARCHAR, owner VARCHAR, base_revision INTEGER, version INTEGER,
    data_json VARCHAR, created_at TIMESTAMP, updated_at TIMESTAMP, updated_by VARCHAR
);
CREATE TABLE bid_presence (draft_id VARCHAR, actor VARCHAR, last_seen TIMESTAMP);
-- The rendered PDF of each revision, archived at submission.
CREATE TABLE bid_revision_pdf (bid_id VARCHAR, revision INTEGER, pdf BLOB);
