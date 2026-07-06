import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "hospital.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create Patients Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        patient_id TEXT PRIMARY KEY,
        name TEXT,
        age INTEGER
    )
    """)

    # Create Doctors Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS doctors (
        doctor_id TEXT PRIMARY KEY,
        name TEXT,
        specialization TEXT
    )
    """)

    # Create Doctor Slots Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS doctor_slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctor_id TEXT,
        slot TEXT,
        is_available BOOLEAN DEFAULT 1,
        FOREIGN KEY(doctor_id) REFERENCES doctors(doctor_id)
    )
    """)

    # Create Appointments Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS appointments (
        appointment_id TEXT PRIMARY KEY,
        patient_id TEXT,
        doctor_id TEXT,
        slot TEXT,
        FOREIGN KEY(patient_id) REFERENCES patients(patient_id),
        FOREIGN KEY(doctor_id) REFERENCES doctors(doctor_id)
    )
    """)

    # Create Lab Reports Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lab_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT,
        test_name TEXT,
        status TEXT,
        FOREIGN KEY(patient_id) REFERENCES patients(patient_id)
    )
    """)

    # Clear existing data for fresh seed
    cursor.execute("DELETE FROM lab_reports")
    cursor.execute("DELETE FROM appointments")
    cursor.execute("DELETE FROM doctor_slots")
    cursor.execute("DELETE FROM doctors")
    cursor.execute("DELETE FROM patients")

    # --- Patients ---
    patients = [
        ("P001", "John Doe", 45),
        ("P002", "Alice Smith", 32),
    ]
    cursor.executemany("INSERT INTO patients (patient_id, name, age) VALUES (?, ?, ?)", patients)

    # --- Doctors: 3 Cardiology + 2 Orthopedics + 3 General Practice (fallback) ---
    doctors = [
        # Cardiology
        ("D101", "Dr. Brown",  "Cardiology"),
        ("D102", "Dr. Patel",  "Cardiology"),
        ("D103", "Dr. Khan",   "Cardiology"),
        # Orthopedics
        ("D104", "Dr. Green",  "Orthopedics"),
        ("D105", "Dr. Lee",    "Orthopedics"),
        # General Practice (fallback for any unmatched specialty)
        ("D201", "Dr. Adams",  "General Practice"),
        ("D202", "Dr. Nair",   "General Practice"),
        ("D203", "Dr. Smith",  "General Practice"),
    ]
    cursor.executemany(
        "INSERT INTO doctors (doctor_id, name, specialization) VALUES (?, ?, ?)", doctors
    )

    # --- Doctor Slots ---
    today = datetime.date.today()
    day0 = today.strftime("%Y-%m-%d")
    day1 = (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    day2 = (today + datetime.timedelta(days=2)).strftime("%Y-%m-%d")
    day3 = (today + datetime.timedelta(days=3)).strftime("%Y-%m-%d")
    day4 = (today + datetime.timedelta(days=4)).strftime("%Y-%m-%d")

    # D101 (Dr. Brown) — first slot taken by A101
    slots = [
        ("D101", f"{day0} 09:00", 0),   # taken
        ("D101", f"{day0} 11:00", 1),
        ("D101", f"{day1} 09:00", 1),
        ("D101", f"{day2} 10:00", 1),
        # D102 (Dr. Patel)
        ("D102", f"{day0} 10:00", 1),
        ("D102", f"{day1} 14:00", 1),
        ("D102", f"{day2} 09:00", 1),
        ("D102", f"{day3} 11:00", 1),
        # D103 (Dr. Khan)
        ("D103", f"{day0} 14:00", 1),
        ("D103", f"{day1} 10:00", 1),
        ("D103", f"{day2} 14:00", 1),
        ("D103", f"{day3} 09:00", 1),
        # D104 (Dr. Green)
        ("D104", f"{day1} 10:00", 1),
        ("D104", f"{day1} 14:00", 1),
        ("D104", f"{day2} 11:00", 1),
        # D105 (Dr. Lee)
        ("D105", f"{day2} 09:00", 1),
        ("D105", f"{day3} 14:00", 1),
        ("D105", f"{day4} 10:00", 1),
        # D201 (Dr. Adams, GP)
        ("D201", f"{day0} 09:00", 1),
        ("D201", f"{day0} 11:00", 1),
        ("D201", f"{day1} 09:00", 1),
        ("D201", f"{day2} 10:00", 1),
        # D202 (Dr. Nair, GP)
        ("D202", f"{day0} 10:00", 1),
        ("D202", f"{day1} 14:00", 1),
        ("D202", f"{day2} 09:00", 1),
        ("D202", f"{day3} 11:00", 1),
        # D203 (Dr. Smith, GP)
        ("D203", f"{day1} 10:00", 1),
        ("D203", f"{day2} 14:00", 1),
        ("D203", f"{day3} 09:00", 1),
        ("D203", f"{day4} 11:00", 1),
    ]
    cursor.executemany(
        "INSERT INTO doctor_slots (doctor_id, slot, is_available) VALUES (?, ?, ?)", slots
    )

    # --- Existing Appointments ---
    appointments = [
        ("A101", "P001", "D101", f"{day0} 09:00"),
    ]
    cursor.executemany(
        "INSERT INTO appointments (appointment_id, patient_id, doctor_id, slot) VALUES (?, ?, ?, ?)",
        appointments,
    )

    # --- Lab Reports ---
    lab_reports = [
        ("P001", "ECG",        "Completed"),
        ("P001", "Blood Test", "Completed"),
    ]
    cursor.executemany(
        "INSERT INTO lab_reports (patient_id, test_name, status) VALUES (?, ?, ?)", lab_reports
    )

    conn.commit()
    conn.close()
    print("Database initialized and seeded successfully.")

if __name__ == "__main__":
    init_db()
