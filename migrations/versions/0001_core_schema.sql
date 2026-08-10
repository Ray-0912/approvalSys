CREATE TABLE IF NOT EXISTS `schedule_comments` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `department` VARCHAR(50) NOT NULL,
    `month_str` VARCHAR(7) NOT NULL,
    `content` TEXT NULL,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `unique_dept_month` (`department`, `month_str`)
);

CREATE TABLE IF NOT EXISTS `salary_rule_version` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `version_name` VARCHAR(100) NOT NULL,
    `effective_from` DATE NOT NULL,
    `overtime_monthly_multiplier` DECIMAL(6,3) NOT NULL DEFAULT 1.330,
    `overtime_hourly_multiplier` DECIMAL(6,3) NOT NULL DEFAULT 1.500,
    `holiday_multiplier` DECIMAL(6,3) NOT NULL DEFAULT 2.000,
    `grace_late_minutes` INT NOT NULL DEFAULT 5,
    `grace_early_minutes` INT NOT NULL DEFAULT 5,
    `regular_hours_staff` DECIMAL(5,2) NOT NULL DEFAULT 8.50,
    `regular_hours_manager` DECIMAL(5,2) NOT NULL DEFAULT 9.00,
    `created_by` INT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`)
);

CREATE TABLE IF NOT EXISTS `employee_salary_profile` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `user_id` INT NOT NULL,
    `salary_type` VARCHAR(20) NOT NULL DEFAULT 'monthly',
    `monthly_salary` DECIMAL(12,2) NULL,
    `hourly_salary` DECIMAL(12,2) NULL,
    `weekday_hourly_rate` DECIMAL(12,2) NULL,
    `holiday_hourly_rate` DECIMAL(12,2) NULL,
    `professional_allowance` DECIMAL(12,2) NULL,
    `position_allowance` DECIMAL(12,2) NULL,
    `base_salary_amount` DECIMAL(12,2) NULL,
    `sales_allowance` DECIMAL(12,2) NULL,
    `overtime_allowance` DECIMAL(12,2) NULL,
    `night_shift_allowance` DECIMAL(12,2) NULL,
    `special_leave_allowance` DECIMAL(12,2) NULL,
    `updated_by` INT NULL,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `unique_user_salary_profile` (`user_id`)
);

CREATE TABLE IF NOT EXISTS `salary_day_rate_override` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `user_id` INT NOT NULL,
    `work_date` DATE NOT NULL,
    `rate` DECIMAL(12,2) NOT NULL,
    `updated_by` INT NULL,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `unique_salary_day_rate_override` (`user_id`, `work_date`)
);

CREATE TABLE IF NOT EXISTS `salary_monthly_result` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `year_month` VARCHAR(7) NOT NULL,
    `user_id` INT NOT NULL,
    `rule_version_id` INT NOT NULL,
    `total_work_minutes` INT NOT NULL DEFAULT 0,
    `regular_minutes` INT NOT NULL DEFAULT 0,
    `overtime_minutes` INT NOT NULL DEFAULT 0,
    `holiday_minutes` INT NOT NULL DEFAULT 0,
    `late_count` INT NOT NULL DEFAULT 0,
    `early_count` INT NOT NULL DEFAULT 0,
    `late_deduction` DECIMAL(12,2) NULL,
    `gross_salary` DECIMAL(12,2) NOT NULL DEFAULT 0,
    `net_salary` DECIMAL(12,2) NOT NULL DEFAULT 0,
    `payroll_status` VARCHAR(20) NOT NULL DEFAULT 'draft',
    `submitted_by` INT NULL,
    `approved_by` INT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `unique_salary_month_user` (`year_month`, `user_id`)
);

CREATE TABLE IF NOT EXISTS `holiday_calendar` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `holiday_date` DATE NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    `country_code` VARCHAR(10) NOT NULL DEFAULT 'TW',
    `created_by` INT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `unique_holiday_date_country` (`holiday_date`, `country_code`)
);

CREATE TABLE IF NOT EXISTS `audit_log` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `entity_type` VARCHAR(50) NOT NULL,
    `entity_id` VARCHAR(50) NOT NULL,
    `action` VARCHAR(50) NOT NULL,
    `changed_by` INT NULL,
    `changed_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `before_json` LONGTEXT NULL,
    `after_json` LONGTEXT NULL,
    `ip_address` VARCHAR(64) NULL,
    `user_agent` VARCHAR(255) NULL,
    PRIMARY KEY (`id`)
);

CREATE TABLE IF NOT EXISTS `role_permissions` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `role_id` INT NOT NULL,
    `permission_key` VARCHAR(100) NOT NULL,
    `allowed` TINYINT(1) NOT NULL DEFAULT 0,
    `updated_by` INT NULL,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `unique_role_permission` (`role_id`, `permission_key`)
);

INSERT INTO role (role_id, name)
SELECT 4, 'Accountant'
WHERE NOT EXISTS (SELECT 1 FROM role WHERE role_id = 4);

INSERT INTO salary_rule_version
(version_name, effective_from, overtime_monthly_multiplier, overtime_hourly_multiplier,
 holiday_multiplier, grace_late_minutes, grace_early_minutes,
 regular_hours_staff, regular_hours_manager, created_by)
SELECT 'default-2026', CURDATE(), 1.330, 1.500, 2.000, 5, 5, 8.50, 9.00, 1
WHERE NOT EXISTS (SELECT 1 FROM salary_rule_version);