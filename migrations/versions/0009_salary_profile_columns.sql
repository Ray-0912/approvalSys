SET @stmt = IF (
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'employee_salary_profile' AND column_name = 'weekday_hourly_rate') = 0,
  'ALTER TABLE employee_salary_profile ADD COLUMN weekday_hourly_rate DECIMAL(12,2) NULL AFTER hourly_salary',
  'SELECT 1'
);
PREPARE stmt FROM @stmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @stmt = IF (
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'employee_salary_profile' AND column_name = 'holiday_hourly_rate') = 0,
  'ALTER TABLE employee_salary_profile ADD COLUMN holiday_hourly_rate DECIMAL(12,2) NULL AFTER weekday_hourly_rate',
  'SELECT 1'
);
PREPARE stmt FROM @stmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @stmt = IF (
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'employee_salary_profile' AND column_name = 'professional_allowance') = 0,
  'ALTER TABLE employee_salary_profile ADD COLUMN professional_allowance DECIMAL(12,2) NULL AFTER holiday_hourly_rate',
  'SELECT 1'
);
PREPARE stmt FROM @stmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @stmt = IF (
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'employee_salary_profile' AND column_name = 'position_allowance') = 0,
  'ALTER TABLE employee_salary_profile ADD COLUMN position_allowance DECIMAL(12,2) NULL AFTER professional_allowance',
  'SELECT 1'
);
PREPARE stmt FROM @stmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @stmt = IF (
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'employee_salary_profile' AND column_name = 'base_salary_amount') = 0,
  'ALTER TABLE employee_salary_profile ADD COLUMN base_salary_amount DECIMAL(12,2) NULL AFTER position_allowance',
  'SELECT 1'
);
PREPARE stmt FROM @stmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @stmt = IF (
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'employee_salary_profile' AND column_name = 'sales_allowance') = 0,
  'ALTER TABLE employee_salary_profile ADD COLUMN sales_allowance DECIMAL(12,2) NULL AFTER base_salary_amount',
  'SELECT 1'
);
PREPARE stmt FROM @stmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @stmt = IF (
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'employee_salary_profile' AND column_name = 'overtime_allowance') = 0,
  'ALTER TABLE employee_salary_profile ADD COLUMN overtime_allowance DECIMAL(12,2) NULL AFTER sales_allowance',
  'SELECT 1'
);
PREPARE stmt FROM @stmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @stmt = IF (
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'employee_salary_profile' AND column_name = 'night_shift_allowance') = 0,
  'ALTER TABLE employee_salary_profile ADD COLUMN night_shift_allowance DECIMAL(12,2) NULL AFTER overtime_allowance',
  'SELECT 1'
);
PREPARE stmt FROM @stmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @stmt = IF (
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'employee_salary_profile' AND column_name = 'special_leave_allowance') = 0,
  'ALTER TABLE employee_salary_profile ADD COLUMN special_leave_allowance DECIMAL(12,2) NULL AFTER night_shift_allowance',
  'SELECT 1'
);
PREPARE stmt FROM @stmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

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
