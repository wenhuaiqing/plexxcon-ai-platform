-- One row per question put to the assistant. The prompt of an anonymous
-- visitor is never stored verbatim: only which agents ran and how it went.
CREATE TABLE agent_run (
    ts TIMESTAMP, page VARCHAR, agents VARCHAR, engine VARCHAR, ok BOOLEAN, error_count INTEGER, duration_ms INTEGER
);
