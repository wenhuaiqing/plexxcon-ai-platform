-- Supplier paperwork. 'inbox' has been received and not yet reviewed; nothing
-- a parser reads reaches the register until a person confirms it.
CREATE TABLE msr_document (
    doc_id VARCHAR, project_id VARCHAR, register VARCHAR, kind VARCHAR, supplier VARCHAR, filename VARCHAR,
    status VARCHAR, received_at TIMESTAMP, received_by VARCHAR, committed_ref VARCHAR
);
CREATE TABLE msr_document_blob (doc_id VARCHAR, pdf BLOB);
