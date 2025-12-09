from database import get_db_connection

def create_tables():
    connection = get_db_connection()
    cursor = connection.cursor()

    # Create shift_type table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shift_type (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(50) NOT NULL,
        start_time TIME NOT NULL,
        end_time TIME NOT NULL,
        color VARCHAR(20) DEFAULT '#007bff',
        is_active BOOLEAN DEFAULT TRUE
    )
    """)

    # Create schedule table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS schedule (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        date DATE NOT NULL,
        shift_type_id INT NOT NULL,
        created_by INT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (shift_type_id) REFERENCES shift_type(id)
    )
    """)

    # Seed default shift types
    cursor.execute("SELECT COUNT(*) FROM shift_type")
    count = cursor.fetchone()[0]

    if count == 0:
        print("Seeding default shift types...")
        default_shifts = [
            ("Morning", "08:00:00", "17:00:00", "#007bff"),   # Blue
            ("Night", "15:00:00", "22:00:00", "#fd7e14"),     # Orange
            ("Big Night", "22:00:00", "08:00:00", "#6f42c1")  # Purple
        ]
        cursor.executemany(
            "INSERT INTO shift_type (name, start_time, end_time, color) VALUES (%s, %s, %s, %s)",
            default_shifts
        )
        connection.commit()
        print("Seeding complete.")
    else:
        print("Shift types already exist. Skipping seed.")

    connection.commit()
    cursor.close()
    connection.close()
    print("Database setup complete.")

if __name__ == "__main__":
    create_tables()
