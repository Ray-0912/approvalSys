from database import get_db_connection

def run_migration():
    sql = """
    CREATE TABLE IF NOT EXISTS `schedule_comments` (
      `id` INT NOT NULL AUTO_INCREMENT,
      `department` VARCHAR(50) NOT NULL,
      `month_str` VARCHAR(7) NOT NULL,
      `content` TEXT NULL,
      `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (`id`),
      UNIQUE KEY `unique_dept_month` (`department`, `month_str`)
    );
    """
    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql)
            connection.commit()
        print("Migration successful")
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    run_migration()
