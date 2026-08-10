-- NOTE:
-- Column additions for employee_salary_profile are handled in
-- 0009_salary_profile_columns.sql with information_schema checks,
-- which works across MySQL variants that do not support
-- ALTER TABLE ... ADD COLUMN IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS salary_day_rate_override (
    id INT NOT NULL AUTO_INCREMENT,
    user_id INT NOT NULL,
    work_date DATE NOT NULL,
    rate DECIMAL(12,2) NOT NULL,
    updated_by INT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY unique_salary_day_rate_override (user_id, work_date)
);
