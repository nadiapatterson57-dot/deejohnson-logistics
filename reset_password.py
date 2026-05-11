import sqlite3
import hashlib
import os

# Database path
db_path = 'logistics.db'

# Connect to database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Create admin table if it doesn't exist
cursor.execute('''
    CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

# Create shipment table if it doesn't exist
cursor.execute('''
    CREATE TABLE IF NOT EXISTS shipment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tracking_code TEXT UNIQUE NOT NULL,
        customer_name TEXT,
        customer_email TEXT,
        customer_phone TEXT,
        origin TEXT,
        destination TEXT,
        package_type TEXT,
        package_weight REAL,
        estimated_delivery TEXT,
        status TEXT,
        current_location TEXT,
        last_update TIMESTAMP,
        partner_courier TEXT,
        partner_tracking TEXT,
        notes TEXT,
        notification_sent BOOLEAN DEFAULT 0
    )
''')

# Create review table if it doesn't exist
cursor.execute('''
    CREATE TABLE IF NOT EXISTS review (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_name TEXT,
        location TEXT,
        rating INTEGER,
        comment TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

# Reset admin password to 'admin123'
new_password = "admin123"
password_hash = hashlib.sha256(new_password.encode()).hexdigest()

# Check if admin exists
cursor.execute("SELECT * FROM admin WHERE username = 'admin'")
admin_exists = cursor.fetchone()

if admin_exists:
    # Update existing admin
    cursor.execute("UPDATE admin SET password_hash = ? WHERE username = 'admin'", (password_hash,))
    print("✅ Admin password updated!")
else:
    # Create new admin
    cursor.execute("INSERT INTO admin (username, password_hash) VALUES (?, ?)", ('admin', password_hash))
    print("✅ Admin user created!")

# Add sample reviews if none exist
cursor.execute("SELECT COUNT(*) FROM review")
review_count = cursor.fetchone()[0]

if review_count == 0:
    sample_reviews = [
        ('Mr. Adebayo Ogunlesi', 'Ibadan', 5, 'Excellent service! My package arrived quickly.'),
        ('Mrs. Funmilayo Adeyemi', 'Oyo Town', 5, 'Best logistics company in Oyo State. Very reliable!'),
        ('Chief Emeka Okonkwo', 'Ibadan', 4, 'Professional clearing and forwarding. Will recommend.'),
    ]
    cursor.executemany("INSERT INTO review (customer_name, location, rating, comment) VALUES (?, ?, ?, ?)", sample_reviews)
    print("✅ Sample reviews added!")

conn.commit()
conn.close()

print("\n" + "="*50)
print("✅ DATABASE SETUP COMPLETE!")
print("="*50)
print(f"📝 Login Credentials:")
print(f"   Username: admin")
print(f"   Password: {new_password}")
print("="*50)
print("\n⚠️  IMPORTANT: Change this password after first login!")