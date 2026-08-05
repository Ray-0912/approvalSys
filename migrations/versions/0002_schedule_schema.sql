CREATE TABLE IF NOT EXISTS shift_type (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    color VARCHAR(20) DEFAULT '#007bff',
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS schedule (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    date DATE NOT NULL,
    shift_type_id INT NOT NULL,
    created_by INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (shift_type_id) REFERENCES shift_type(id)
);

INSERT INTO shift_type (name, start_time, end_time, color)
SELECT 'Morning', '08:00:00', '17:00:00', '#007bff'
WHERE NOT EXISTS (SELECT 1 FROM shift_type);

INSERT INTO shift_type (name, start_time, end_time, color)
SELECT 'Night', '15:00:00', '22:00:00', '#fd7e14'
WHERE NOT EXISTS (SELECT 1 FROM shift_type WHERE name = 'Night');

INSERT INTO shift_type (name, start_time, end_time, color)
SELECT 'Big Night', '22:00:00', '08:00:00', '#6f42c1'
WHERE NOT EXISTS (SELECT 1 FROM shift_type WHERE name = 'Big Night');