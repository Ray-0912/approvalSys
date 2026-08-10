CREATE TABLE IF NOT EXISTS employee_professional_allowance_map (
    user_id INT NOT NULL,
    item_id INT NOT NULL,
    updated_by INT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, item_id),
    KEY idx_epam_item_id (item_id),
    CONSTRAINT fk_epam_user FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_epam_item FOREIGN KEY (item_id) REFERENCES professional_allowance_item(id) ON DELETE CASCADE
);
