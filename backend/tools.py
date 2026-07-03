import sqlite3
import os
import uuid
from typing import List, Dict, Any
from langchain_core.tools import tool

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "hospital.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@tool
def get_patient_details(patient_id: str) -> Dict[str, Any]:
    """Fetches patient details, existing appointments, and lab reports from the database given a patient_id."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM patients WHERE patient_id = ?", (patient_id,))
    patient_row = cursor.fetchone()
    if not patient_row:
        conn.close()
        return {"error": f"Patient with ID {patient_id} not found."}
    
    patient = dict(patient_row)
    
    cursor.execute("SELECT * FROM appointments WHERE patient_id = ?", (patient_id,))
    patient["appointments"] = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM lab_reports WHERE patient_id = ?", (patient_id,))
    patient["lab_reports"] = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return patient

# Map the words patients use to the specializations stored in the database.
# Any symptom or word not in this map falls back to General Practice.
SPECIALIZATION_SYNONYMS = {
    "cardiologist": "cardiology",
    "cardiac": "cardiology",
    "heart": "cardiology",
    "chest": "cardiology",
    "orthopedist": "orthopedics",
    "orthopaedic": "orthopedics",
    "orthopedic": "orthopedics",
    "bone": "orthopedics",
    "joint": "orthopedics",
    # GP synonyms
    "general": "general practice",
    "gp": "general practice",
    "general practitioner": "general practice",
    "general practice": "general practice",
    # Symptoms that should route to GP as fallback
    "stomach": "general practice",
    "fever": "general practice",
    "pain": "general practice",
    "cold": "general practice",
    "flu": "general practice",
    "headache": "general practice",
    "cough": "general practice",
    "fatigue": "general practice",
    "nausea": "general practice",
    "vomiting": "general practice",
    "diarrhea": "general practice",
    "back pain": "general practice",
}


def _match_specialization(query: str, stored: str) -> bool:
    """Fuzzy match a requested specialty against a stored specialty."""
    q = SPECIALIZATION_SYNONYMS.get(query.strip().lower(), query.strip().lower())
    s = stored.strip().lower()
    if q in s or s in q:
        return True
    # Fall back to a shared word root (e.g. "cardio").
    return q[:5] != "" and q[:5] == s[:5]


def _next_patient_id() -> str:
    """Compute the next sequential patient id like P003 based on existing rows."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT patient_id FROM patients")
    max_num = 0
    for row in cursor.fetchall():
        pid = row["patient_id"]
        if pid and pid[1:].isdigit():
            max_num = max(max_num, int(pid[1:]))
    conn.close()
    return f"P{max_num + 1:03d}"


@tool
def register_patient(name: str, age: int) -> Dict[str, Any]:
    """Registers a new patient with the given name and age.

    Auto-generates a new patient_id and returns it. Use this when a patient is
    new or their provided id does not exist.
    """
    patient_id = _next_patient_id()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO patients (patient_id, name, age) VALUES (?, ?, ?)",
        (patient_id, name, age),
    )
    conn.commit()
    conn.close()
    return {
        "status": "Success",
        "patient_id": patient_id,
        "name": name,
        "age": age,
        "message": f"Registered {name} with patient id {patient_id}.",
    }


def _get_all_doctors_with_slots(cursor, specialization_filter: str = None) -> List[Dict[str, Any]]:
    """Helper: fetch doctors (optionally filtered) with their available slots."""
    cursor.execute("SELECT * FROM doctors")
    all_rows = cursor.fetchall()
    if specialization_filter:
        rows = [r for r in all_rows if _match_specialization(specialization_filter, r["specialization"])]
    else:
        rows = list(all_rows)
    doctors = []
    for row in rows:
        d = dict(row)
        cursor.execute(
            "SELECT slot FROM doctor_slots WHERE doctor_id = ? AND is_available = 1",
            (d["doctor_id"],)
        )
        d["available_slots"] = [r["slot"] for r in cursor.fetchall()]
        doctors.append(d)
    return doctors


@tool
def search_doctors(specialization: str) -> List[Dict[str, Any]]:
    """Finds doctors by specialization and returns their details along with available slots.

    If no specialist matches, automatically falls back to General Practice doctors.
    """
    conn = get_connection()
    cursor = conn.cursor()

    doctors = _get_all_doctors_with_slots(cursor, specialization)

    if not doctors:
        # Auto-fallback: return General Practice doctors with a fallback note.
        gp_doctors = _get_all_doctors_with_slots(cursor, "general practice")
        conn.close()
        if gp_doctors:
            for d in gp_doctors:
                d["fallback"] = True
                d["fallback_reason"] = (
                    f"No {specialization} specialist available. "
                    "Showing General Practitioners instead."
                )
            return gp_doctors
        return [{"error": f"No doctors found for '{specialization}' and no GPs available."}]

    conn.close()
    return doctors

@tool
def book_appointment(patient_id: str, doctor_id: str, slot: str) -> Dict[str, Any]:
    """Books an appointment for a patient with a specific doctor at a specific slot."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Fetch doctor info for a friendly response
    cursor.execute("SELECT name, specialization FROM doctors WHERE doctor_id = ?", (doctor_id,))
    doctor_row = cursor.fetchone()
    doctor_name = doctor_row["name"] if doctor_row else doctor_id
    specialization = doctor_row["specialization"] if doctor_row else ""

    # Check if slot is still available
    cursor.execute(
        "SELECT id FROM doctor_slots WHERE doctor_id = ? AND slot = ? AND is_available = 1",
        (doctor_id, slot)
    )
    slot_row = cursor.fetchone()
    
    if not slot_row:
        conn.close()
        return {"error": f"Slot {slot} is not available for {doctor_name}. Please try another slot."}
        
    appointment_id = f"A{uuid.uuid4().hex[:4].upper()}"
    
    # Mark slot as unavailable
    cursor.execute("UPDATE doctor_slots SET is_available = 0 WHERE id = ?", (slot_row["id"],))
    
    # Create appointment
    cursor.execute(
        "INSERT INTO appointments (appointment_id, patient_id, doctor_id, slot) VALUES (?, ?, ?, ?)",
        (appointment_id, patient_id, doctor_id, slot)
    )
    
    conn.commit()
    conn.close()
    return {
        "status": "Success",
        "appointment_id": appointment_id,
        "doctor_name": doctor_name,
        "specialization": specialization,
        "slot": slot,
        "message": f"Appointment {appointment_id} booked with {doctor_name} ({specialization}) on {slot}.",
    }

@tool
def check_lab_reports(patient_id: str, test_name: str) -> Dict[str, Any]:
    """Checks if a specific lab report exists for a patient. Use test_name like 'ECG' or 'Blood Test'."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT * FROM lab_reports WHERE patient_id = ? AND test_name LIKE ?", 
        (patient_id, f"%{test_name}%")
    )
    reports = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    if not reports:
        return {"exists": False, "message": f"No {test_name} report found for patient {patient_id}."}
    return {"exists": True, "reports": reports}

@tool
def schedule_lab_test(patient_id: str, test_name: str) -> Dict[str, Any]:
    """Schedules a new lab test for a patient."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO lab_reports (patient_id, test_name, status) VALUES (?, ?, ?)",
        (patient_id, test_name, "Scheduled")
    )
    
    conn.commit()
    conn.close()
    return {"status": "Success", "message": f"{test_name} scheduled for patient {patient_id}."}

@tool
def send_notification(patient_id: str, message: str) -> Dict[str, Any]:
    """Sends a final notification to the patient with a summary message. Use this only when all tasks are complete."""
    # Simulate sending a notification
    print(f"[NOTIFICATION to {patient_id}]: {message}")
    return {"status": "Sent", "message": "Notification delivered successfully."}
