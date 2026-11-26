-- Page count is recorded when a document finishes parsing.
ALTER TABLE documents ADD COLUMN page_count INTEGER;
