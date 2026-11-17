-- A supplier's own document API, simulated: what the supplier has published
-- for our jobs. The register pulls from it and never writes to it. In
-- production this is the supplier's REST API, not a table.
CREATE TABLE supplier_feed (
    external_ref VARCHAR, supplier VARCHAR, project_id VARCHAR, register VARCHAR, kind VARCHAR,
    filename VARCHAR, published_at TIMESTAMP, pdf BLOB
);
-- How each document arrived: 'email' (the mailbox import), 'upload', or 'api'.
-- external_ref is the supplier's own id for a document pulled from its API, so
-- a second sync never saves it twice.
ALTER TABLE msr_document ADD COLUMN source VARCHAR DEFAULT 'email';
ALTER TABLE msr_document ADD COLUMN external_ref VARCHAR;
