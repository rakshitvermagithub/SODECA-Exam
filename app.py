from authlib.integrations.flask_client import OAuth
from cs50 import SQL
from config import Config
from datetime import datetime, date
from flask import Flask, flash, redirect, render_template, request, session, url_for, jsonify, send_from_directory
from flask_session import Session
from functools import wraps
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import os
import sys


app = Flask(__name__)
app.config.from_object(Config)
Session(app)

app.secret_key = app.config["SECRET_KEY"]

GOOGLE_CLIENT_ID = app.config["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = app.config["GOOGLE_CLIENT_SECRET"]

DRIVE_CLIENT_ID = app.config["DRIVE_CLIENT_ID"]
DRIVE_CLIENT_SECRET = app.config["DRIVE_CLIENT_SECRET"]

# --- UNIFIED OAUTH 2.0 SETUP (USING AUTHLIB ONLY) ---
oauth = OAuth(app)

# Client 1: For User Login (Students & Faculty) - Minimal Permissions
google_login_client = oauth.register(
    name='google_login', # A unique name for this client
    client_id = GOOGLE_CLIENT_ID,
    client_secret = GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)
# Client 2: For Faculty Drive Access - Specific, Powerful Permission
google_drive_client = oauth.register(
    name='google_drive', # A unique name for this client
    client_id = DRIVE_CLIENT_ID, # IMPORTANT: Use a SEPARATE Client ID
    client_secret = DRIVE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'https://www.googleapis.com/auth/drive.file'},
)

# --- General App Configuration ---
UPLOAD_FOLDER = app.config["UPLOAD_FOLDER"]
PARENT_FOLDER_ID = "1cllojwiiMV2_YtZ93eadi0rrHf6Lg6_-" # Your target Google Drive folder
db = SQL(f"sqlite:///{app.config['DATABASE_FILE']}")

def login_required(f):
    """
    Decorate routes to require login.
    https://flask.palletsprojects.com/en/3.0.x/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


# Allowed extensions for the certificate upload
ALLOWED_EXTENSIONS = app.config["ALLOWED_EXTENSIONS"]
def allowed_file(filename):
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Form Fields Defined
FORM_DEFINITIONS = {
    'blood_donor': {
        'title': 'Blood Donor',
        'description': '...',
        'enctype': 'multipart/form-data',  # Important for file uploads
        'fields': [
            {
                'field_label': 'Event Title',
                'field_type': 'text',
                'field_name': 'event_title',
                'required': True,  # Boolean instead of string
                'placeholder': 'e.g., Blood Donation Camp 2024',
                'help_text': 'Name of the blood donation event or campaign',
                'field_validation': {
                    'min_length': 3,
                    'max_length': 50
                }
            },
            {
                'field_label': 'From Date',
                'field_type': 'date',
                'field_name': 'from_date',
                'required': True,
                'help_text': 'Start date of the donation event',
                'field_validation': {
                    'max_date': 'today'  # Can't be future date
                }
            },
            {
                'field_label': 'To Date',
                'field_type': 'date',
                'field_name': 'to_date',
                'required': True,
                'help_text': 'End date of the donation event',
                'field_validation': {
                    'max_date': 'today',
                    'after_field': 'from_date'  # Must be after from_date
                }
            },
            {
                'field_label': 'Organizer',
                'field_type': 'text',
                'field_name': 'organizer',
                'required': True,
                'placeholder': 'e.g. SKIT',
                'help_text': 'Organization that conducted the blood donation drive',
                'field_validation': {
                    'min_length': 3,
                    'max_length': 150
                }
            },
            {
                'field_label': 'Venue',
                'field_type': 'text',
                'field_name': 'venue',
                'required': True,
                'placeholder': 'e.g. Civil block, SKIT, Jaipur',
                'help_text': 'Location where blood donation took place',
                'field_validation': {
                    'min_length': 5,
                    'max_length': 200
                }
            },
            {
                'field_label': 'Certificate / Proof',
                'field_type': 'file',
                'field_name': 'certificate',
                'required': True,
                'help_text': 'Upload your blood donor certificate or equivalent proof',
                'validation': {
                    'accepted_types': ['.pdf', '.jpg', '.jpeg', '.png'],
                    'max_size': '5MB'
                }
            }
        ]
    },

    'part_in_comp': {
        'title': 'Participation in Competition/Contest/Activity',
        'description': '...',
        'enctype': 'multipart/form-data',  # Important for file uploads
        'fields': [
            {
                'field_label': 'Name of the Competition/Event/Activity',
                'field_type': 'text',
                'field_name': 'event_title',
                'required': True,  # Boolean instead of string
                'placeholder': 'e.g., Blood Donation Camp 2024',
                'help_text': 'Exactly as Mentioned in the Certificate e.g : SUR, Mayukh, Kill With Fire, Game of Quizzes, Mahatma Gandhi Quiz',
                'field_validation': {
                    'min_length': 3,
                    'max_length': 50
                }
            },
            {
                'field_label': 'Nature of the Event',
                'field_type': 'text',
                'field_name': 'event_nature',
                'required': True,
                'help_text': 'e.g Dance Competition, Singing Competition, Quiz Competition, Tree Plantation Event',
            },
            {
                'field_label': 'Team/Individual',
                'field_type': 'radio',
                'field_name': 'participation_type',
                'required': True,
                'options': [
                    {'value': 'Team', 'label': 'Team'},
                    {'value': 'Individual', 'label': 'Individual'},
                ]
            },
            {
                'field_label': 'Event Level',
                'field_type': 'radio',
                'field_name': 'event_level',
                'required': True,
                'placeholder': 'e.g. SKIT',
                'help_text': '''College Level : Event within SKIT only. No other college/university participated.
                    University Level : Only RTU affiliated college participated.
                    State Level : Different colleges/universities  all over Rajasthan participated.
                    National Level : Colleges/Universities outside the Rajasthan (all over from India) participated.
                    International : Colleges/Universities outside India (all over the world ) participated.''',
                'options': [
                    {'value': 'College', 'label': 'College'},
                    {'value': 'University', 'label': 'University'},
                    {'value': 'State', 'label': 'State'},
                    {'value': 'National', 'label': 'National'},
                    {'value': 'International', 'label': 'International'},
                ]
            },
            {
                'field_label': 'Event Type',
                'field_type': 'radio',
                'field_name': 'event_type',
                'required': True,
                'options': [
                    {'value': 'Intra College', 'label': 'Intra College'},
                    {'value': 'Inter College', 'label': 'Inter College'},
                ]
            },
            {
                'field_label': 'Event Category',
                'field_type': 'radio',
                'field_name': 'event_category',
                'required': True,
                'options': [
                    {'value': 'Cultural', 'label': 'Cultural'},
                    {'value': 'Technical', 'label': 'Technical'},
                    {'value': 'Sports', 'label': 'Sports'},
                    {'value': 'Non-Technical', 'label': 'Non-Technical'},
                ]
            },
            {
                'field_label': 'Mode of Event',
                'field_type': 'radio',
                'field_name': 'event_mode',
                'required': True,
                'options': [
                    {'value': 'Online', 'label': 'Online'},
                    {'value': 'Offline', 'label': 'Offline'},
                ]
            },
            {
                'field_label': 'Event Duration(in days)',
                'field_type': 'number',
                'field_name': 'event_duration',
                'required': True,
                'placeholder': 'Your answer',
                'field_validation': {
                    'min': 1,
                    'max': 365
                }
            },
            {
                'field_label': 'From Date',
                'field_type': 'date',
                'field_name': 'from_date',
                'required': True,
                'help_text': 'Start date of the donation event',
                'field_validation': {
                    'max_date': 'today'  # Can't be future date
                }
            },
            {
                'field_label': 'To Date',
                'field_type': 'date',
                'field_name': 'to_date',
                'required': True,
                'help_text': 'End date of the donation event',
                'field_validation': {
                    'max_date': 'today',
                    'after_field': 'from_date'  # Must be after from_date
                }
            },
            {
                'field_label': 'Organizer',
                'field_type': 'text',
                'field_name': 'organizer',
                'required': True,
                'placeholder': 'e.g. SKIT, Jaipur',
                'help_text': 'Organization that conducted the event',
                'field_validation': {
                    'min_length': 3,
                    'max_length': 150
                }
            },
            {
                'field_label': 'Venue',
                'field_type': 'text',
                'field_name': 'venue',
                'required': True,
                'placeholder': 'e.g. Civil block, SKIT, Jaipur',
                'help_text': 'Location where blood donation took place',
                'field_validation': {
                    'min_length': 5,
                    'max_length': 200
                }
            },
            {
                'field_label': 'Certificate/Proof',
                'field_type': 'file',
                'field_name': 'certificate',
                'required': True,
                'help_text': 'Upload your participation certificate or equivalent proof',
                'validation': {
                    'accepted_types': ['.pdf'],
                    'max_size': '5MB'
                }
            }
        ]
    },
    
    'part_in_work': {
        'title': 'Workshop/Seminar/Webinar/Conference Attended',
        'description': '...',
        'enctype': 'multipart/form-data',  # Important for file uploads
        'fields': [
            {
                'field_label': 'Event Name',
                'field_type': 'text',
                'field_name': 'event_title',
                'required': True,  # Boolean instead of string
                'placeholder': '',
                'help_text': 'e.g : Ten Days TEQIP-III Sponsored Student Workshop on Emerging Web Development Trends',
                'field_validation': {
                    'min_length': 3,
                    'max_length': 50
                }
            },
            {
                'field_label': 'Event Type',
                'field_type': 'radio',
                'field_name': 'event_type',
                'required': True,
                'options': [
                    {'value': 'workshop', 'label': 'Workshop'},
                    {'value': 'seminar', 'label': 'Seminar'},
                    {'value': 'webinar', 'label': 'Webinar'},
                    {'value': 'conference', 'label': 'Conference'},
                    {'value': 'symposium', 'label': 'Symposium'},
                ]
            },
            {
                'field_label': 'Level',
                'field_type': 'radio',
                'field_name': 'event_level',
                'required': True,
                'options': [
                    {'value': 'national', 'label': 'National'},
                    {'value': 'international', 'label': 'International'},
                ]
            },
            {
                'field_label': 'Duration(in days)',
                'field_type': 'number',
                'field_name': 'event_duration',
                'required': True,
                'placeholder': 'Your answer',
                'field_validation': {
                    'min': 1,
                    'max': 365
                }
            },
                        {
                'field_label': 'From Date',
                'field_type': 'date',
                'field_name': 'from_date',
                'required': True,
                'help_text': 'Start date of the event',
                'field_validation': {
                    'max_date': 'today'  # Can't be future date
                }
            },
            {
                'field_label': 'To Date',
                'field_type': 'date',
                'field_name': 'to_date',
                'required': True,
                'help_text': 'End date of the event',
                'field_validation': {
                    'max_date': 'today',
                    'after_field': 'from_date'  # Must be after from_date
                }
            },
            {
                'field_label': 'Mode of Event',
                'field_type': 'radio',
                'field_name': 'mode',
                'required': True,
                'options': [
                    {'value': 'online', 'label': 'Online'},
                    {'value': 'offline', 'label': 'Offline'},
                ]
            },
            {
                'field_label': 'Sponsoring Agency',
                'field_type': 'text',
                'field_name': 'sponsor',
                'required': True,  # Boolean instead of string
                'placeholder': '',
                'help_text': 'e.g:TEQIP-III/RTU/AICTE/IEEE/Non Sponsored/NA',
                'field_validation': {
                    'min_length': 3,
                    'max_length': 50
                }
            },
            {
                'field_label': 'Organized By',
                'field_type': 'text',
                'field_name': 'organizer',
                'required': True,  # Boolean instead of string
                'placeholder': '',
                'help_text': 'e.g SKIT Jaipur/ Write online if online activity',
                'field_validation': {
                    'min_length': 3,
                    'max_length': 50
                }
            },
            {
                'field_label': 'Workshop/Seminar/Webinar/Conference Certificate/other proof',
                'field_type': 'file',
                'field_name': 'certificate',
                'required': True,
                'help_text': 'Upload your participation certificate or equivalent proof',
                'validation': {
                    'accepted_types': ['.pdf'],
                    'max_size': '5MB'
                }
            }
        ]
    }
}

# List of technical names of forms defined
form_name_list = list(FORM_DEFINITIONS.keys())
# List of title names of forms defined
form_title = []
for form in FORM_DEFINITIONS:
    form_title.append(FORM_DEFINITIONS[form]["title"])

# Initialise table to store student login details
db.execute("""
    CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    email TEXT UNIQUE NOT NULL, hash_password TEXT, google_id TEXT UNIQUE,
    auth_provider TEXT DEFAULT 'local' NOT NULL, profile_picture TEXT,
    first_name TEXT, last_name TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, role TEXT NOT NULL DEFAULT 'student'
    CHECK (role IN ('student', 'faculty', 'admin')))
""")
# Initialise table to store student details
db.execute("""
    CREATE TABLE IF NOT EXISTS student_details(student_user_id INTEGER PRIMARY KEY NOT NULL,
    university_roll_no TEXT NOT NULL, student_name TEXT NOT NULL, branch TEXT NOT NULL,
    semester INTEGER NOT NULL, section TEXT NOT NULL, class_group TEXT NOT NULL,
    batch_counselor TEXT NOT NULL, FOREIGN KEY (student_user_id) REFERENCES users(user_id))
""")
# Initialise table to store faculty details
db.execute("""
    CREATE TABLE IF NOT EXISTS faculty_details(
        full_name TEXT NOT NULL, 
        college_email TEXT PRIMARY KEY,
        designation TEXT NOT NULL,
        department TEXT NOT NULL, 
        assigned_batch TEXT NOT NULL DEFAULT 'not assigned',
        contact TEXT NOT NULL DEFAULT 'to be updated'
        )
    """)

# Create tables for all the forms in FORM_DEFINITIONS
for form in form_name_list:

    # Check if table named the form exists
    table_exists = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", form)

    # If not exists
    if not table_exists:

        # List to store differnet fields definition
        col_def_list = []
        for field_col in FORM_DEFINITIONS[form]["fields"]:

            field_col_name = field_col["field_name"]

            # Defining form fields with dataype TEXT and is REQUIRED
            col_def = f"{field_col_name} TEXT NOT NULL"
            col_def_list.append(col_def)

        # SQL string
        field_cols_sql = ",".join(col_def_list)

        # Dynamically create SQL tables for all forms
        db.execute(
            f"""CREATE TABLE IF NOT EXISTS {form}(
            student_id INTEGER PRIMARY KEY NOT NULL,
            {field_cols_sql},
            full_path TEXT NOT NULL,
            google_file_id TEXT NOT NULL DEFAULT 'pending',
            status TEXT DEFAULT 'pending' NOT NULL,
            FOREIGN KEY (student_id) REFERENCES student_details(student_user_id),
            CHECK (status IN ('pending', 'approved', 'rejected'))
            )"""
        )

# Returns if user is student, faculty or admin
def role(user_id):
    role = db.execute("SELECT role FROM users WHERE user_id = ?", user_id)[0]['role']
    return role

def local_delete(full_path):
    try:
        # Security check - ensure the file is within UPLOAD_FOLDER
        # This prevents directory traversal attacks
        if not os.path.abspath(full_path).startswith(os.path.abspath(UPLOAD_FOLDER)):
            print(f"Security violation: Attempted to delete file outside upload folder: {full_path}")
            return redirect("/faculty_dashboard")

        # Check if file exists before attempting deletion
        if not os.path.exists(full_path):
            print(f"File does not exist: {full_path}")
            return redirect("/faculty_dashboard")

        # Check if it's actually a file (not a directory)
        if not os.path.isfile(full_path):
            print(f"Path is not a file: {full_path}")
            return redirect("/faculty_dashboard")

        # Delete the file
        os.remove(full_path)
        print(f"Entry rejected and successfully deleted file: {full_path}")
        flash("Entry rejected", "danger")
        return redirect("/faculty_dashboard")

    except IndexError:
        print(f"No record found or invalid data structure for in form {form}")
        flash("Database error: Record not found.", "danger")
        return redirect(url_for('faculty_dashboard'))

    except PermissionError:
        print(f"Permission denied when trying to delete file: {full_path}")
        flash("Permission denied: Cannot delete the file.", "danger")
        return redirect(url_for('faculty_dashboard'))

    except OSError as e:
        print(f"OS error when deleting file {full_path}: {e}")
        flash("System error occurred while deleting the file.", "danger")
        return redirect(url_for('faculty_dashboard'))

    except Exception as e:
        print(f"Unexpected error in local_delete: {e}")
        flash("An unexpected error occurred. Please try again.", "danger")
        return redirect(url_for('faculty_dashboard'))
    
# Get list of faculty emails
faculty_emails = []
faculty_dict = db.execute("SELECT college_email FROM faculty_details")
for faculty in faculty_dict:
    faculty_emails.append(faculty["college_email"])

# Register
@app.route("/register", methods=["GET", "POST"])
def register():

    # If POST request
    if request.method == "POST":

        # email id
        email = request.form.get("email")
        if not email or '@' not in email:
            # Flash error message
            flash("Please enter a valid email address", "danger")
            return redirect("/register")

        # password
        password = request.form.get("password")
        if not password:
            # Flash error message
            return redirect("/register")

        # confirm password
        confirm_password = request.form.get("confirm_password")
        if not confirm_password:
            # Flash error message
            return redirect("/register")

        # if pass = confirm pass
        if password != confirm_password:
            # Flash error message
            return redirect("/register")

        # Check if email already exists
        existing_user = db.execute("SELECT * FROM users WHERE email = ?", email)
        if existing_user:
            flash("Email already registered", "danger")
            return render_template("register.html")

        # If form was filled successfully
        # Convert plain password into a complex string
        hash_password = generate_password_hash(password)

        if email in faculty_emails:
            # Store Faculty's login details in the table
            db.execute(
                "INSERT INTO users (email, hash_password, role) VALUES (?, ?, ?)", email, hash_password, 'faculty'
                )
            return redirect(url_for("faculty_dashboard"))
        else:
            # Store Student's login details in the table
            db.execute(
                "INSERT INTO users (email, hash_password) VALUES (?, ?)", email, hash_password,
                )
            return redirect("/student_details")
    else:
        return render_template("register.html")

@app.route("/auth/google")
def google_login():
    """Handles user LOGIN. Asks only for profile information."""
    redirect_uri = url_for('login_callback', _external=True)
    return google_login_client.authorize_redirect(redirect_uri)

@app.route("/auth/google/callback")
def login_callback():
    """Handles the callback for the user LOGIN flow."""
    try:
        token = google_login_client.authorize_access_token()
        # The user's login info is now in token['userinfo']
        user_info = token.get('userinfo')

        if user_info:
            # --- Your existing logic to handle user creation/login ---
            google_id = user_info['sub']
            email = user_info['email']
            first_name = user_info.get('given_name', '')
            last_name = user_info.get('family_name', '')
            profile_picture = user_info.get('picture', '')

            is_faculty = email in faculty_emails

            # Check if user already exists with this Google ID
            existing_user = db.execute("SELECT * FROM users WHERE google_id = ?", google_id)

            if existing_user:
                # User exists, log them into the application session
                session["user_id"] = existing_user[0]["user_id"]
                session["auth_provider"] = "google"
                flash("Logged in successfully with Google!", "success")
            else:
                # No user with this Google ID, check if the email is already registered
                email_user = db.execute("SELECT * FROM users WHERE email = ?", email)
                if email_user:
                    # Email exists, link this Google ID to the existing account
                    db.execute("""
                        UPDATE users SET google_id = ?, profile_picture = ?, first_name = ?, last_name = ?,
                        auth_provider = 'google', updated_at = CURRENT_TIMESTAMP
                        WHERE email = ?
                    """, google_id, profile_picture, first_name, last_name, email)
                    session["user_id"] = email_user[0]["user_id"]
                    flash("Google account linked successfully!", "success")
                else:
                    if is_faculty:
                        # New faculty, create a new account in the database with role 'faculty'
                        user_id = db.execute("""
                            INSERT INTO users (email, google_id, auth_provider, profile_picture, first_name, last_name, role)
                            VALUES (?, ?, 'google', ?, ?, ?, ?)
                        """, email, google_id, profile_picture, first_name, last_name, "faculty")
                        session["user_id"] = user_id
                        flash("Welcome Faculty! Account created with Google!", "success")
                        return redirect(url_for("faculty_dashboard"))
                    else:
                        # New student, create a new account in the database with default role 'student'
                        user_id = db.execute("""
                            INSERT INTO users (email, google_id, auth_provider, profile_picture, first_name, last_name)
                            VALUES (?, ?, 'google', ?, ?, ?)
                        """, email, google_id, profile_picture, first_name, last_name)

                    session["user_id"] = user_id
                    flash("Welcome Student! Account created with Google!", "success")
                    return redirect("/student_details")
                
            if is_faculty:
                return redirect(url_for("faculty_dashboard"))
            
            return redirect(url_for("sodeca_forms")) # Or wherever users go after login
        else:
            flash("Could not fetch user info from Google.", "danger")
            return redirect("/login")
    except Exception as e:
        flash(f"Authentication failed: {e}", "danger")
        return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    # Forget any past user
    session.clear()

    if request.method == "POST":

        email = request.form.get("email")
        if not email or '@' not in email:
            flash("Invalid email", "danger")
            return redirect("/register")

        password = request.form.get("password")
        if not password:
            flash("Password is required", "danger")
            return redirect("/login")

        rows = db.execute(
            "SELECT * FROM users WHERE email=? AND auth_provider = 'local'", email
            )

        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash_password"], password
            ):
            flash("Invalid email or password", "danger")
            return redirect("/register")

        # Remember the user if login was successful
        session["user_id"] = rows[0]["user_id"]
        session["auth_provider"] = "local"

        if email in faculty_emails:
            return redirect(url_for("faculty_dashboard"))
        else:
            return redirect(url_for("sodeca_forms"))
    else:
        return render_template("login.html")

@app.route('/authorize_drive')
def authorize_drive():
    """Handles Drive AUTHORIZATION for faculty. Asks only for Drive permission."""
    redirect_uri = url_for('drive_callback', _external=True)
    return google_drive_client.authorize_redirect(redirect_uri)

@app.route('/auth/google/drive_callback')
def drive_callback():
    """Handles the callback for the faculty DRIVE authorization flow."""
    try:
        # 1. Fetch the token from Google.
        token = google_drive_client.authorize_access_token()

        # 2. Explicitly save the token into our own custom session key.
        session['drive_auth_token'] = token
        flash("Google Drive has been successfully authorized.", "success")
    except Exception as e:
        flash(f"Drive authorization failed: {e}", "danger")

    return redirect(url_for('faculty_dashboard'))

@app.route("/logout")
@login_required
def logout():
    # Always clear session - this is safe even if session is empty
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect("/login")

@app.route("/student_details", methods=["GET", "POST"])
@login_required
def student_details():

    # If user wants to insert or update data
    if request.method == "POST":

        # Get University Roll No.
        university_roll_no = request.form.get("university_roll_no")
        if not university_roll_no:
            return redirect("/student_details")

        # Get
        student_name = request.form.get("student_name")
        if not student_name:
            return redirect("/student_details")

        # Get Branch
        selected_branch = request.form.get("branch_option")
        if not selected_branch:
            return redirect("/student_details")

        # Get Semester
        selected_semester = request.form.get("semester_option")
        if not selected_semester:
            return redirect("/student_details")

        # Get Section
        selected_section = request.form.get("section_option")
        if not selected_section:
            return redirect("/student_details")

        # Get Group
        selected_group = request.form.get("group_option")
        if not selected_group:
            return redirect("/student_details")

        # Get Batch Counselor name
        batch_counselor = request.form.get("batch_counselor")
        if not batch_counselor:
            return redirect("/student_details")

        # If all entries are filled successfuly

        # Create student_details table if not there
        # roll no. columns is not unique because if one student makes any mistake
        # that will create hurdles for others
        db.execute(
            "CREATE TABLE IF NOT EXISTS student_details(student_user_id INTEGER PRIMARY KEY NOT NULL, " \
            "university_roll_no TEXT NOT NULL, student_name TEXT NOT NULL, branch TEXT NOT NULL, " \
            "semester INTEGER NOT NULL, section TEXT NOT NULL, class_group TEXT NOT NULL, " \
            "batch_counselor TEXT NOT NULL, FOREIGN KEY (student_user_id) " \
            "REFERENCES users(user_id))"
            )

        # Store detail using UPSERT query
        # The corrected and robust "UPSERT" command
        db.execute(
            """
            INSERT INTO student_details (
                student_user_id, university_roll_no, student_name, branch,
                semester, section, class_group, batch_counselor
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(student_user_id) DO UPDATE SET
                university_roll_no = excluded.university_roll_no,
                student_name = excluded.student_name,
                branch = excluded.branch,
                semester = excluded.semester,
                section = excluded.section,
                class_group = excluded.class_group,
                batch_counselor = excluded.batch_counselor
            """,
            session["user_id"], university_roll_no, student_name, selected_branch,
            selected_semester, selected_section, selected_group, batch_counselor
        )
        flash("Your details are saved successfully, you may proceed to the homepage.", "success")
        return redirect("/student_details")

    else:

        # Get student details if already present
        # Variable stores a list of dictionaries
        student_details_row = db.execute(
            "SELECT * FROM student_details WHERE student_user_id = ?", session["user_id"]
        )

        # If details are already available
        if student_details_row:
            filled_details = student_details_row[0]

            # Show the page with filled details
            return render_template(
                "student_details.html", details = filled_details
                )
        else:
            return render_template("student_details.html", details=None)

@app.route("/", methods=["GET", "POST"])
def sodeca_forms():

    if request.method == "POST":
        selected_forms = request.form.getlist('selected_forms[]') # e.g., ['form1', 'form3', 'form5']

        # Store the list and the starting point (index 0) in the session
        session['selected_forms'] = selected_forms
        session['current_form_index'] = 0

        # redirect to fill form
        return redirect("/verify_student_details")
    else:
        return render_template("sodeca_forms.html")

@app.route("/verify_student_details", methods=["GET", "POST"])
@login_required
def verify_student_details():

    if session["user_id"]:

        # If student checked and clicked next
        if request.method == "POST":

            verified_details = request.form.get("verified_details")
            session["verified_details"] = verified_details

            print(f"Verified: {verified_details}")

            if verified_details == None:
                flash("Kindly confirm details by checking the checkbox", "warning")
                return redirect("/verify_student_details")
            else:
                return redirect("/fill_form")
        else:
            # Get student details if already present
            # Variable stores a list of dictionaries
            student_details_row = db.execute(
                        "SELECT * FROM student_details WHERE student_user_id = ?", session["user_id"]
                        )

            # If details are already available
            if student_details_row:
                filled_details = student_details_row[0]

                # Show the page with filled details
                return render_template("verify_student_details.html", details = filled_details)
            else:
                return render_template("verify_student_details.html", details=None)

@app.route("/fill_form", methods=["GET", "POST"])
@login_required
def fill_form():

    user_id = session["user_id"]

    if user_id:

        # If not selected any forms, first go and select
        if "selected_forms" not in session:
            flash("Please select atleast one form to submit", "danger")
            return redirect("/")

        # Verify if student checked the verification checkbox
        if "verified_details" not in session:
            flash('Please verify you student details', "warning")
            return redirect("/verify_student_details")

        # If verification was not checked
        if not session["verified_details"]:
            flash("Please check the checkbox to confirm your details", "danger")
            return redirect("/verify_student_details")

        selected_forms = session["selected_forms"]
        current_form_index = session["current_form_index"]

        # If all forms are completed
        if current_form_index >= len(selected_forms):

            # Clean up the session
            session.pop("selected_forms", None)
            session.pop("current_form_index", None)

            flash("Kindly check your submissions and their approval status on the hompeage", "success")
            return redirect("/")

        # current_form_index is the key in dict "selected_forms" defined in the start
        current_form = selected_forms[current_form_index]
        form_to_show = FORM_DEFINITIONS[current_form]

        if request.method == "POST":

            # Initialise dict for text and radio inputs
            form_inputs = {}

            # Initialise in this scope the google_file_id
            save_path = ""

            # Check if certificate was submitted
            if 'certificate' not in request.files:
                flash("No file part", "danger")
                return redirect(request.url)

            # Iterating through all input fields
            for field in form_to_show["fields"]:

                field_title = field["field_label"]
                field_name = field["field_name"]
                field_type = field["field_type"]

                # If input field is a date
                if field_type == "date":
                    date_string = request.form.get(field_name)
                    try:
                        # Parse the date string into a datetime object
                        date_object = datetime.strptime(date_string, '%Y-%m-%d').date()

                        if field_name == "to_date":
                            to_date = date_object
                        if field_name == "from_date":
                            from_date = date_object

                        # After succesful parsing only, Append in form_inputs
                        form_inputs[field_name] = date_string

                    except ValueError:
                        flash("Invalid date format submitted.")
                        return redirect(request.url)

                elif field_type == "file":

                    # As certificate is required in every form
                    certificate = request.files[field_name]

                    # Check if the user selected a file
                    if certificate.filename == "":
                        flash("No selected file", "danger")
                        return redirect(request.url)

                    # Check if file is valid and has an allowed extension
                    if certificate and allowed_file(certificate.filename):

                        # Get student_name and unversity_roll_no
                        student_details = db.execute(
                            """SELECT university_roll_no, student_name FROM
                            student_details WHERE student_user_id = ?""", user_id
                        )

                        # Get file extension eg. ".pdf"
                        file_extension = os.path.splitext(certificate.filename)[1]

                        # Rename the file in format universityroll_studentname_eventname
                        uni_roll_no = student_details[0]["university_roll_no"]
                        student_name = student_details[0]["student_name"]
                        event_name = request.form.get("event_title", "unknown_event")

                        certificate.filename =  f"{uni_roll_no}_{student_name}_{event_name}{file_extension}"

                        # Secure the filename to prevent security risks (e.g., directory traversal)
                        filename = secure_filename(certificate.filename)
                        # Save filename in form_inputs
                        form_inputs[field_name] = filename

                        save_path = os.path.join(UPLOAD_FOLDER, filename)

                        # Save the file to the local server
                        certificate.save(save_path)

                    else:
                        flash("Invalid file type. Allowed types are: pdf", "danger")
                        return redirect(request.url)

                # Text and Radio inputs
                else:
                    # Update form_inputs dict
                    form_inputs[field_name] = request.form.get(field_name)

                    # If any input is missing
                    if not form_inputs[field_name]:
                        # flash error
                        flash(f"Submission Failed: {field_title} is missing!", "danger")
                        return redirect(request.url)

                    # Debugging
                    print(f"{field_title}: {form_inputs[field_name]}")

                    # TODO: Error Handling

            # Error checking using "date_object"
            if from_date > to_date:
                print(f"from_date: {from_date} > to_date: {to_date} ")
                flash("Error: From date is greater than To date", "danger")
                return redirect(request.url)
            today = date.today()
            if from_date > today or to_date > today:
                print(f"today: {today}, from_date: {from_date}, to_date: {to_date} ")
                flash("Error: Dates cannot be for in future activites", "danger")
                return redirect(request.url)

            if save_path:

                form_fields = form_inputs.keys()
                form_fields_sql = ",".join(form_fields) # Make a list of inputs separated by ","
                placeholder_sql = ",".join(["?"]*len(form_inputs)) # eg. "?,?,?..."
                values_list = list(form_inputs.values()) # eg. ["Value1", "Value2"...]
                # eg. "field1 = excluded.field1, field2 = excluded.field2..."
                update_clause = ", ".join([f"{field} = excluded.{field}" for field in form_fields])

                try:
                    # Dynamically store form entries in respective tables in database
                    db.execute(f"""
                        INSERT INTO {current_form} (student_id, {form_fields_sql}, full_path, google_file_id, status)
                        VALUES(?, {placeholder_sql}, ?, ?, ?)
                        ON CONFLICT(student_id) DO UPDATE SET {update_clause},
                        full_path = EXCLUDED.full_path,
                        google_file_id = EXCLUDED.google_file_id,
                        status = EXCLUDED.status
                    """, session["user_id"], *values_list, # *values_list gives a string eg. "Value1", "Value2"...
                    save_path, "pending", "pending", )

                except Exception as e:
                    print(f"Database error: {e}", file=sys.stderr)
                    flash("A database error occurred while saving the form. Please try again.", "danger")

                    # IMPORTANT: If the DB save fails, we should delete the file we just uploaded

                    return redirect(request.url)

            # Update form number
            session["current_form_index"] += 1

            # Form submission successful, show success page
            return render_template("fill_form.html", success=True, form_to_show=form_to_show)

        # Just show the form to be filled
        return render_template("fill_form.html", success=False, form_to_show=form_to_show)

    else:

        flash("Please Login/Register first")
        return redirect("/login")

# Page for the faculty, to check submissions
# Faculty can do get and post request
@app.route("/faculty_dashboard", methods=["GET"])
@login_required
def faculty_dashboard():

        if request.method == "GET":

            if role(session["user_id"]) != 'faculty':
                return "Access Denied!", 400

            is_authorized = 'drive_auth_token' in session
            print(session.get('drive_auth_token'))
            print(is_authorized)
            if not is_authorized:
                flash("Drive authorization is required. Please authorize your account first", "warning")

            # Empty list to store data from each form in db
            all_forms_data = []
    
            # Get all forms available in form's definitions
            for form in form_name_list:
                # Get the data for different forms
                form_data = db.execute(f"SELECT * FROM {form}")
                # Append it in list of differnet forms' with data
                all_forms_data.append(form_data)

            return render_template("faculty_dashboard.html", forms_data=all_forms_data,
                                   form_title_list=form_title,
                                   form_names=form_name_list,
                                   is_authorized=is_authorized)
        else:
            return redirect("/")

@app.route('/view_submission/<path:filename>') 
@login_required
def view_submission(filename):

    """Securely serves a file from the local upload folder for faculty to view."""
    if role(session["user_id"]) != 'faculty':
        return "Access Denied: You must be a faculty member to view submissions.", 403

    try:
        # send_from_directory is the secure way to send files.
        # It prevents users from accessing files outside the LOCAL_UPLOAD_FOLDER.
        return send_from_directory(
            UPLOAD_FOLDER,
            filename,
            as_attachment=False  # False = view in browser, True = force download
        )
    except FileNotFoundError:
        flash("Error: The requested file could not be found on the server.", "danger")
        return redirect(url_for('faculty_dashboard'))

@app.route("/upload_to_drive", methods=["POST"])
def upload_to_drive():
    """Uploads a file using the authorized Drive client."""
    token = session.get('drive_auth_token')
    if not token:
        flash("Drive authorization required. Please authorize your account first.", "warning")
        return redirect(url_for('faculty_dashboard'))

    filename = request.form.get('filename')
    student_id = request.form.get('student_id')
    form_name = request.form.get('form_name')
    print(filename)
    print(UPLOAD_FOLDER)
    full_path = os.path.join(UPLOAD_FOLDER, filename)

    if not os.path.exists(full_path):
        flash(f"Error: Local file not found at {full_path}", "danger")
        return redirect(url_for('faculty_dashboard'))

    try:
        creds_data = token.copy()
        if 'access_token' in creds_data:
            creds_data['token'] = creds_data.pop('access_token')
        creds_data.pop('scope', None)
        creds_data.pop('userinfo', None)
        creds_data.pop('expires_at', None)
        creds_data.pop('expires_in', None)
        creds_data.pop('token_type', None)

        credentials = Credentials(**creds_data)

        drive_service = build('drive', 'v3', credentials=credentials)

        file_metadata = {'name': filename, 'parents': [PARENT_FOLDER_ID]}
        media = MediaFileUpload(full_path, resumable=True)

        uploaded_file = drive_service.files().create(
            body=file_metadata, media_body=media, fields='id,name'
        ).execute()

        google_file_id = uploaded_file.get('id')

        sql_query = f"UPDATE {form_name} SET status = :status, google_file_id = :gfid WHERE student_id = :sid"
        db.execute(sql_query, status="approved", gfid=google_file_id, sid=student_id)

        flash(f"Successfully uploaded file '{uploaded_file.get('name')}' (ID: {google_file_id})", "success")

    except HttpError as error:
        # This error happens if the token is expired, invalid, or revoked.
        if error.resp.status in [400, 401]:
            # The token is bad. Remove it from the session.
            session.pop('drive_auth_token', None)
            # Send the user a helpful message and prompt them to log in again.
            flash("Your Google authorization has expired or was revoked. Please authorize again.", "warning")
            # Redirecting to the dashboard will now show the "Login with Google" button.
            return redirect(url_for('faculty_dashboard'))
        else:
            # For other API errors (e.g., 500 server error), just show the error.
            flash(f"An API error occurred: {error}", "danger")

    except Exception as e:
        print(f"An unexpected error occurred in upload_to_drive: {e}", file=sys.stderr)
        flash(f"An unexpected error occurred: {e}", "danger")

    return redirect(url_for('faculty_dashboard'))

@app.route("/reject_entry", methods=["POST"])
def reject_entry():
    student_id = request.form.get("student_id")
    form_name = request.form.get("form_name")
    full_path = request.form.get("full_path")
    try:
        db.execute(f"UPDATE {form_name} SET status='rejected' WHERE student_id=?", student_id)
    except Exception as e:
        flash(f"Database error: {e}")
        return redirect(url_for('faculty_dashboard'))
    local_delete(full_path)
    return redirect(url_for('faculty_dashboard'))

@app.route("/super_admin", methods=["GET"])
@login_required
def super_admin():
    return render_template("super_admin.html")

@app.route("/faculty_list", methods=["GET", "POST"])
def faculty_list():
    if request.method == "POST":
        # Add/Update request
        full_name = request.form.get("full_name")
        college_email = request.form.get("college_email")
        designation = request.form.get("designation")
        department = request.form.get("department")
        contact = request.form.get("contact")
        if not contact:
            contact = 'to be updated'

        try:
            db.execute(
                """
                INSERT INTO faculty_details (
                    full_name, college_email, designation, department, contact
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(college_email) DO UPDATE SET
                    full_name = excluded.full_name,
                    designation = excluded.designation,
                    department = excluded.department,
                    contact = excluded.contact
                """,
                full_name, college_email, designation, department, contact
            )
            faculty_emails.append(college_email)
        except Exception as e:
            flash(f"Error updating: {e}")

        # Upload excel
        return redirect(url_for('faculty_list'))
    else:
        faculty_data = db.execute("SELECT * FROM faculty_details")
        return render_template("faculty_list.html", faculty_data=faculty_data)

@app.route("/assign_batch", methods=["GET", "POST"])
@login_required
def assign_batch():

    if request.method == "POST":

        college_email = request.form.get("college_email")
        batch = request.form.get("batch")

        try:
            # Update batch in database
            db.execute("UPDATE faculty_details SET assigned_batch=? WHERE college_email=?", batch, college_email)
            flash("Batch updated!", "success")
        except Exception as e:
            flash(f"Error updating: {e}", "danger")
        
        print("here")
        return redirect (url_for("assign_batch"))
    
    else:

        faculty_data = db.execute("SELECT full_name, college_email, assigned_batch FROM faculty_details")

        for faculty in faculty_data:
            print(faculty["full_name"])
            print(faculty["college_email"])
        return render_template("assign_batch.html", faculty_data=faculty_data)
    
@app.route("/student_report", methods=["GET", "POST"])
@login_required
def student_report():
    if request.method == "GET":
        return render_template("student_report.html")

if __name__ == '__main__':

    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    app.run(host="0.0.0.0", debug=True)

