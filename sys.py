from flask import Flask, render_template, request, redirect, url_for, flash, session
import pandas as pd
import hashlib
import os
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # More secure secret key generation

# File paths
DATA_DIR = "school_data"
os.makedirs(DATA_DIR, exist_ok=True)

USER_FILE = os.path.join(DATA_DIR, "users.csv")
STUDENT_FILE = os.path.join(DATA_DIR, "students.csv")
ATTENDANCE_FILE = os.path.join(DATA_DIR, "attendance.csv")
GRADES_FILE = os.path.join(DATA_DIR, "grades.csv")
FEES_FILE = os.path.join(DATA_DIR, "fees.csv")
TIMETABLE_FILE = os.path.join(DATA_DIR, "timetable.csv")

# Ensure files are initialized
def initialize_file(file_path, columns):
    if not os.path.exists(file_path) or os.stat(file_path).st_size == 0:
        pd.DataFrame(columns=columns).to_csv(file_path, index=False)

initialize_file(USER_FILE, ["role", "pin"])
initialize_file(STUDENT_FILE, ["Name", "Class", "Age", "Gender", "Mobile"])
initialize_file(ATTENDANCE_FILE, ["Name", "Date", "Status", "Remarks"])
initialize_file(GRADES_FILE, ["Name", "Subject", "Marks", "Grade", "Remarks"])
initialize_file(FEES_FILE, ["Name","Amount","Status"])
initialize_file(TIMETABLE_FILE, ["Day", "Time", "Subject", "Instructor"])

# Hash function for security
def hash_pin(pin):
    return hashlib.sha256(pin.encode()).hexdigest()

def verify_user(role, pin):
    if os.path.exists(USER_FILE) and os.stat(USER_FILE).st_size > 0:
        users = pd.read_csv(USER_FILE)
        hashed_pin = hash_pin(pin)
        user = users[(users["role"] == role) & (users["pin"] == hashed_pin)]
        return not user.empty
    return False

def require_role(allowed_roles):
    """Decorator to check user role and permissions"""
    def decorator(f):
        def wrapper(*args, **kwargs):
            role = session.get('role')
            if not role:
                flash("Please log in first.", "danger")
                return redirect(url_for('login'))
            
            if role not in allowed_roles:
                flash("Unauthorized access!", "danger")
                return redirect(url_for('login'))
            
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

def save_dataframe(df, file_path):
    """Helper function to save DataFrame with error handling"""
    try:
        df.to_csv(file_path, index=False)
        return True
    except Exception as e:
        flash(f"Error saving data: {str(e)}", "danger")
        return False

def load_dataframe(file_path):
    """Helper function to load DataFrame"""
    try:
        return pd.read_csv(file_path).to_dict('records')                                                     
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return []

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/authenticate', methods=['POST'])
def authenticate():
    role = request.form.get('role')
    pin = request.form.get('pin')

    if not role or not pin:
        flash("Role or PIN is missing.", "danger")
        return redirect(url_for('login'))

    if verify_user(role, pin):
        # Store role in session
        session['role'] = role
        flash(f"Welcome, {role.capitalize()}!", "success")
        return redirect(url_for('dashboard'))
    else:
        flash("Invalid credentials.", "danger")
        return redirect(url_for('login'))

@app.route('/dashboard')
@require_role(['admin', 'teacher', 'student'])
def dashboard():
    role = session['role']

    if role == 'admin':
        users = load_dataframe(USER_FILE)
        return render_template('dashboard.html', users=users)
    elif role == 'teacher':
        timetable = load_dataframe(TIMETABLE_FILE)
        attendance = load_dataframe(ATTENDANCE_FILE)
        return render_template('teacher_dashboard.html', timetable=timetable, attendance=attendance)
    elif role == 'student':
        grades = load_dataframe(GRADES_FILE)
        attendance = load_dataframe(ATTENDANCE_FILE)
        return render_template('student_dashboard.html', grades=grades, attendance=attendance)
    
@app.route('/enroll_student', methods=['GET', 'POST'])
@require_role(['admin'])
def enroll_student():
    if request.method == 'POST':
        student_name = request.form.get('student_name')
        student_class = request.form.get('student_class')
        student_age = request.form.get('student_age')
        student_gender = request.form.get('student_gender')
        student_mobile = request.form.get('student_mobile')

        if all([student_name, student_class, student_age, student_gender, student_mobile]):
            student_data = pd.DataFrame([{
                "Name": student_name, "Class": student_class, "Age": student_age,
                "Gender": student_gender, "Mobile": student_mobile
            }])
            if os.path.exists(STUDENT_FILE):
                existing_data = pd.read_csv(STUDENT_FILE)
                student_data = pd.concat([existing_data, student_data], ignore_index=True)
            student_data.to_csv(STUDENT_FILE, index=False)
            flash("Student enrolled successfully!", "success")
            return redirect(url_for('dashboard', role='admin'))
        else:
            flash("All fields are required.", "danger")

    return render_template('enroll_student.html')

@app.route('/manage_fees', methods=['GET', 'POST'])
@require_role(['admin'])
def manage_fees():
    if request.method == 'POST':
        student_name = request.form.get('student_name')
        amount = request.form.get('amount')
        status = request.form.get('status')

        if all([student_name, amount, status]):
            try:
                amount = float(amount)
                fee_data = pd.DataFrame([{
                    "Name": student_name,
                    "Amount": amount,
                    "Status": status
                }])
                
                if os.path.exists(FEES_FILE):
                    existing_data = pd.read_csv(FEES_FILE)
                    # Update existing record if it exists, otherwise append new record
                    if existing_data[existing_data['Name'] == student_name].empty:
                        fee_data = pd.concat([existing_data, fee_data], ignore_index=True)
                    else:
                        existing_data.loc[existing_data['Name'] == student_name, ['Amount', 'Status']] = [amount, status]
                        fee_data = existing_data
                
                fee_data.to_csv(FEES_FILE, index=False)
                flash("Fees updated successfully!", "success")
            except ValueError:
                flash("Please enter a valid amount.", "danger")
            return redirect(url_for('manage_fees'))
        else:
            flash("All fields are required.", "danger")

    # Get list of students and fees
    students = pd.read_csv(STUDENT_FILE)['Name'].tolist() if os.path.exists(STUDENT_FILE) else []
    fees = pd.read_csv(FEES_FILE) if os.path.exists(FEES_FILE) else pd.DataFrame(columns=['Name', 'Amount', 'Status'])
    
    # Calculate summary statistics
    total_collected = fees[fees['Status'] == 'Paid']['Amount'].sum()
    pending_amount = fees[fees['Status'] == 'Pending']['Amount'].sum()
    overdue_amount = fees[fees['Status'] == 'Overdue']['Amount'].sum()
    
    return render_template('manage_fees.html', 
                         students=students, 
                         fees=fees.to_dict('records'),
                         total_collected=total_collected,
                         pending_amount=pending_amount,
                         overdue_amount=overdue_amount)

@app.route('/manage_attendance', methods=['GET', 'POST'])
@require_role(['admin', 'teacher'])
def manage_attendance():
    if request.method == 'POST':
        student_name = request.form.get('student_name')
        date = request.form.get('date')
        status = request.form.get('status')
        remarks = request.form.get('remarks', '')

        if all([student_name, date, status]):
            try:
                # Read existing attendance data
                attendance_data = pd.read_csv(ATTENDANCE_FILE) if os.path.exists(ATTENDANCE_FILE) and os.stat(ATTENDANCE_FILE).st_size > 0 else pd.DataFrame()

                # Check for existing record
                mask = (attendance_data['Name'] == student_name) & (attendance_data['Date'] == date)
                
                if mask.any():
                    # Update existing record
                    attendance_data.loc[mask, ['Status', 'Remarks']] = [status, remarks]
                else:
                    # Append new record
                    new_record = pd.DataFrame([{
                        "Name": student_name,
                        "Date": date,
                        "Status": status,
                        "Remarks": remarks
                    }])
                    attendance_data = pd.concat([attendance_data, new_record], ignore_index=True)

                # Save to file
                if save_dataframe(attendance_data, ATTENDANCE_FILE):
                    flash("Attendance marked successfully!", "success")
                    return redirect(url_for('manage_attendance'))
            except Exception as e:
                flash(f"Error managing attendance: {str(e)}", "danger")

    # Load students & attendance records
    students = pd.read_csv(STUDENT_FILE)['Name'].tolist() if os.path.exists(STUDENT_FILE) else []
    attendance_records = load_dataframe(ATTENDANCE_FILE)

    return render_template('manage_attendance.html', students=students, attendance_records=attendance_records)


@app.route('/manage_timetable', methods=['GET', 'POST'])
@require_role(['admin', 'teacher'])
def manage_timetable():
    if request.method == 'POST':
        day = request.form.get('day')
        time = request.form.get('time')
        subject = request.form.get('subject')
        instructor = request.form.get('instructor')

        if all([day, time, subject, instructor]):
            try:
                # Read existing timetable data
                timetable_data = pd.read_csv(TIMETABLE_FILE) if os.path.exists(TIMETABLE_FILE) and os.stat(TIMETABLE_FILE).st_size > 0 else pd.DataFrame()
                # Ensure required columns exist
                required_columns = ['Day', 'Time', 'Subject', 'Instructor']
                if timetable_data.empty:
                 timetable_data = pd.DataFrame(columns=required_columns)
                else:
                 for col in required_columns:
                  if col not in timetable_data.columns:
                    timetable_data[col] = ""

                # Check for existing record
                mask = ((timetable_data['Day'] == day) & 
                        (timetable_data['Time'] == time) & 
                        (timetable_data['Subject'] == subject))
                
                if mask.any():
                    # Update existing record
                    timetable_data.loc[mask, 'Instructor'] = instructor
                else:
                    # Append new record
                    new_record = pd.DataFrame([{
                        "Day": day,
                        "Time": time,
                        "Subject": subject,
                        "Instructor": instructor
                    }])
                    timetable_data = pd.concat([timetable_data, new_record], ignore_index=True)

                # Save the timetable data
                if save_dataframe(timetable_data, TIMETABLE_FILE):
                    flash("Timetable updated successfully!", "success")
                    return redirect(url_for('manage_timetable'))
            except Exception as e:
                flash(f"Error saving timetable: {str(e)}", "danger")
        else:
            flash("All fields are required.", "danger")

    # Load timetable records
    timetable_records = load_dataframe(TIMETABLE_FILE)

    return render_template('manage_timetable.html', timetable_records=timetable_records)

@app.route('/manage_grades', methods=['GET', 'POST'])
@require_role(['admin', 'teacher'])
def manage_grades():
    # Load students for the dropdown
    try:
        students = pd.read_csv(STUDENT_FILE)['Name'].tolist()
    except (pd.errors.EmptyDataError, FileNotFoundError):
        students = []

    if request.method == 'POST':
        student_name = request.form.get('student_name')
        subject = request.form.get('subject')
        grade = request.form.get('grade')
        remarks = request.form.get('remarks', '')

        if all([student_name, subject, grade]):
            try:
                # Read existing grades data
                grade_data = pd.read_csv(GRADES_FILE) if os.path.exists(GRADES_FILE) and os.stat(GRADES_FILE).st_size > 0 else pd.DataFrame()

                # Check for existing record
                mask = ((grade_data['Name'] == student_name) & 
                        (grade_data['Subject'] == subject))
                
                if mask.any():
                    # Update existing record
                    grade_data.loc[mask, ['Grade', 'Remarks']] = [grade, remarks]
                else:
                    # Append new record
                    new_record = pd.DataFrame([{
                        "Name": student_name,
                        "Subject": subject,
                        "Grade": grade,
                        "Remarks": remarks,
                        "Marks": None  # Placeholder for potential future marks calculation
                    }])
                    grade_data = pd.concat([grade_data, new_record], ignore_index=True)

                # Save the grade data
                if save_dataframe(grade_data, GRADES_FILE):
                    flash("Grade updated successfully!", "success")
                    return redirect(url_for('manage_grades'))
            except Exception as e:
                flash(f"Error saving grades: {str(e)}", "danger")
        else:
            flash("All fields are required.", "danger")

    # Load grade records
    grade_records = load_dataframe(GRADES_FILE)

    return render_template('manage_grades.html', students=students, grade_records=grade_records)
@app.route('/create_admin', methods=['GET', 'POST'])
def create_admin():
    if request.method == 'POST':
        student_pin = request.form.get('student_pin')
        teacher_pin = request.form.get('teacher_pin')

        if student_pin and teacher_pin:
            try:
                # Read existing user data
                users_data = pd.read_csv(USER_FILE) if os.path.exists(USER_FILE) else pd.DataFrame()

                # Create admin data
                admin_data = pd.DataFrame([{
                    "role": "admin",
                    "pin": hash_pin(student_pin)
                }])

                # Combine existing and new data
                users_data = pd.concat([users_data, admin_data], ignore_index=True)

                # Save to file
                if save_dataframe(users_data, USER_FILE):
                    flash("Admin account created successfully!", "success")
                    return redirect(url_for('login'))
            except Exception as e:
                flash(f"Error creating admin account: {str(e)}", "danger")
        else:
            flash("Both fields are required.", "danger")

    return render_template('create_admin.html')

@app.route('/create_student', methods=['GET', 'POST'])
def create_student():
    if request.method == 'POST':
        student_pin = request.form.get('student_pin')

        if student_pin:
            try:
                # Read existing user data
                users_data = pd.read_csv(USER_FILE) if os.path.exists(USER_FILE) else pd.DataFrame()

                # Create student data
                student_data = pd.DataFrame([{
                    "role": "student",
                    "pin": hash_pin(student_pin)
                }])

                # Combine existing and new data
                users_data = pd.concat([users_data, student_data], ignore_index=True)

                # Save to file
                if save_dataframe(users_data, USER_FILE):
                    flash("Student account created successfully!", "success")
                    return redirect(url_for('login'))
            except Exception as e:
                flash(f"Error creating student account: {str(e)}", "danger")
        else:
            flash("Student PIN is required.", "danger")

    return render_template('create_student.html')

@app.route('/create_teacher', methods=['GET', 'POST'])
def create_teacher():
    if request.method == 'POST':
        teacher_pin = request.form.get('teacher_pin')

        if teacher_pin:
            try:
                # Read existing user data
                users_data = pd.read_csv(USER_FILE) if os.path.exists(USER_FILE) else pd.DataFrame()

                # Create teacher data
                teacher_data = pd.DataFrame([{
                    "role": "teacher",
                    "pin": hash_pin(teacher_pin)
                }])

                # Combine existing and new data
                users_data = pd.concat([users_data, teacher_data], ignore_index=True)

                # Save to file
                if save_dataframe(users_data, USER_FILE):
                    flash("Teacher account created successfully!", "success")
                    return redirect(url_for('login'))
            except Exception as e:
                flash(f"Error creating teacher account: {str(e)}", "danger")
        else:
            flash("Teacher PIN is required.", "danger")

    return render_template('create_teacher.html')

@app.route('/mark_bulk_attendance', methods=['POST'])
def mark_bulk_attendance():
    date = request.form.get('date')
    if not date:
        flash("Date is required.", "danger")
        return redirect(url_for('manage_bulk_attendance'))

    students = pd.read_csv(STUDENT_FILE)['Name'].tolist() if os.path.exists(STUDENT_FILE) else []
    attendance_data = []

    for student in students:
        status = request.form.get(f'status_{student}')
        remarks = request.form.get(f'remarks_{student}', '')
        if status:
            attendance_data.append({
                "Name": student,
                "Date": date,
                "Status": status,
                "Remarks": remarks
            })

    if attendance_data:
        df = pd.DataFrame(attendance_data)
        if os.path.exists(ATTENDANCE_FILE):
            existing_data = pd.read_csv(ATTENDANCE_FILE)
            # Remove any existing records for the same date
            existing_data = existing_data[existing_data['Date'] != date]
            df = pd.concat([existing_data, df], ignore_index=True)
        df.to_csv(ATTENDANCE_FILE, index=False)
        flash("Bulk attendance marked successfully!", "success")
    else:
        flash("No attendance data to save.", "danger")

    return redirect(url_for('manage_attendance'))

if __name__ == '__main__':
    app.run(debug=True)