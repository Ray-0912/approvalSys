ALTER TABLE schedule ADD INDEX idx_schedule_user_date (user_id, date);

ALTER TABLE document ADD INDEX idx_document_status (status);

ALTER TABLE document ADD INDEX idx_document_create_time (create_time);

ALTER TABLE doc_approval_record ADD INDEX idx_approval_user_status (pk_user_id, status);