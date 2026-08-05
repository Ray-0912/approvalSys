CREATE TABLE IF NOT EXISTS `schedule_off_request` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `user_id` INT NOT NULL,
    `request_date` DATE NOT NULL,
    `note` VARCHAR(200) NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'pending',
    `reviewed_by` INT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `unique_user_date` (`user_id`, `request_date`)
);

CREATE TABLE IF NOT EXISTS `scheduling_constraint` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `team_id` INT NOT NULL,
    `shift_type_id` INT NOT NULL,
    `min_count` INT NOT NULL DEFAULT 1,
    `created_by` INT NULL,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `unique_team_shift` (`team_id`, `shift_type_id`)
);
