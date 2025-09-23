from authlib.integrations.flask_client import OAuth
from cs50 import SQL
from config import Config
from datetime import datetime
from flask import Flask, flash, redirect, render_template, request, session, url_for, jsonify
from flask_session import Session
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import csv
import os

app = Flask(__name__)
app.config.from_object(Config)
Session(app)

app.secret_key = app.config["SECRET_KEY"]

GOOGLE_CLIENT_ID = app.config["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = app.config["GOOGLE_CLIENT_SECRET"]

# To upload certificates
UPLOAD_FOLDER = app.config["UPLOAD_FOLDER"]

# TODO: Are session setting configured?

db_path = app.config['DATABASE_FILE']
with open(db_path, 'a'):
    pass  
  
# Database configuration
db = SQL(f"sqlite:///{db_path}")

# Allowed extensions for the certificate upload
ALLOWED_EXTENSIONS = app.config["ALLOWED_EXTENSIONS"]

# OAuth Setup
oauth = OAuth(app)

google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

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

    'participation': {
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
    }
}

# List of technical names of forms defined
form_name_list = FORM_DEFINITIONS.keys()

# List of title names of forms defined
form_title = []
for form in FORM_DEFINITIONS:
    form_title.append(FORM_DEFINITIONS[form]["title"])

# Create tables for all the forms in FORM_DEFINITIONS
# Iterate through all forms defined
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
            status TEXT DEFAULT 'pending' NOT NULL, 
            FOREIGN KEY (student_id) REFERENCES student_details(student_user_id),
            CHECK (status IN ('pending', 'approved', 'rejected'))
            )"""
        )

def allowed_file(filename):
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Register
@app.route("/", methods=["GET", "POST"])
def register():
    
    # If POST request
    if request.method == "POST":

        # email id
        email = request.form.get("email")
        if not email or '@' not in email:
            # Flash error message
            flash("Please enter a valid email address", "error")
            return redirect("/")
        
        # password
        password = request.form.get("password")
        if not password:
            # Flash error message
            return redirect("/")
        
        # confirm password
        confirm_password = request.form.get("confirm_password")
        if not confirm_password:
            # Flash error message
            return redirect("/")
        
        # if pass = confirm pass
        if password != confirm_password:
            # Flash error message
            return redirect("/")
        
        # Check if email already exists
        existing_student = db.execute("SELECT * FROM students WHERE email = ?", email)
        if existing_student:
            flash("Email already registered", "error")
            return render_template("register.html")
        
        # If form was filled successfully
        # Convert plain password into a complex string 
        hash_password = generate_password_hash(password)

        # Create "students" table if it is not there
        db.execute(
            "CREATE TABLE IF NOT EXISTS students (" \
            "user_id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, email TEXT UNIQUE NOT NULL, " \
            "hash_password TEXT, google_id TEXT UNIQUE, auth_provider TEXT DEFAULT 'local' NOT NULL, " \
            "profile_picture TEXT, first_name TEXT, last_name TEXT, " \
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
            )
        # Store Student's login details in the table
        db.execute(
            "INSERT INTO students (email, hash_password) VALUES (?, ?)", email, hash_password 
            )
        return redirect("/login")
    else:
        return render_template("register.html")

@app.route("/auth/google")
def google_login():
    redirect_uri = url_for('callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route("/login", methods=["GET", "POST"])
def login():
    # Forget any past user
    session.clear()

    if request.method == "POST":

        email = request.form.get("email")
        if not email or '@' not in email:
            flash("Invalid email")
            return redirect("/")

        password = request.form.get("password")
        if not password:
            flash("Password is required")
            return redirect("/login")
        
        rows = db.execute(
            "SELECT * FROM students WHERE email=? AND auth_provider = 'local'", email
            )
        
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash_password"], password
            ):
            return redirect("/login")

        # Remember the user if login was successful
        session["user_id"] = rows[0]["user_id"]
        session["auth_provider"] = "local"

        return redirect("/student_details")
    else:
        return render_template("login.html")
    
@app.route("/auth/google/callback")
def callback():
    """Handle Google OAuth callback"""
    try:
        token = google.authorize_access_token()

        user_info_url = 'https://openidconnect.googleapis.com/v1/userinfo'
        resp = google.get(user_info_url, token=token)
        user_info = resp.json()
        
        if user_info:
            google_id = user_info['sub']
            email = user_info['email']
            first_name = user_info.get('given_name', '')
            last_name = user_info.get('family_name', '')
            profile_picture = user_info.get('picture', '')

            # Check if student already exists with Google ID
            existing_student = db.execute("SELECT * FROM students WHERE google_id = ?", google_id)
            
            if existing_student:
                # Student exists, log them in
                session["user_id"] = existing_student[0]["user_id"]
                session["auth_provider"] = "google"
                flash("Logged in successfully with Google!", "success")
                return redirect("/sodeca_forms")
            else:
                # Check if student exists with same email but different auth provider
                email_student = db.execute("SELECT * FROM students WHERE email = ?", email)
                
                if email_student:
                    # Link Google account to existing account
                    db.execute("""
                        UPDATE students 
                        SET google_id = ?, profile_picture = ?, first_name = ?, last_name = ?, 
                            auth_provider = 'google', updated_at = CURRENT_TIMESTAMP
                        WHERE email = ?
                    """, google_id, profile_picture, first_name, last_name, email)
                    
                    session["user_id"] = email_student[0]["user_id"]
                    session["auth_provider"] = "google"
                    flash("Google account linked successfully!", "success")
                    return redirect("/sodeca_forms")
                else:
                    # Create new student
                    user_id = db.execute("""
                        INSERT INTO students (email, google_id, auth_provider, profile_picture, first_name, last_name)
                        VALUES (?, ?, 'google', ?, ?, ?)
                    """, email, google_id, profile_picture, first_name, last_name)
                    
                    session["user_id"] = user_id
                    session["auth_provider"] = "google"

                    flash("Welcome! Account created successfully with Google!", "success")
                    flash("You may fill your details", "info")
                    return redirect("/student_details")
        else:
            flash("Failed to get user information from Google", "error")
            return redirect("/login")
            
    except Exception as e:
        flash(f"Authentication failed: {str(e)}", "error")
        return redirect("/login")

@app.route("/logout")
def logout():
    # Always clear session - this is safe even if session is empty
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect("/login")

@app.route("/student_details", methods=["GET", "POST"])
def student_details():

    # If user is logged in, give access to page
    if session["user_id"]:

        # If user wants to insert or update data
        if request.method == "POST":

            # Get University Roll No.
            university_roll_no = request.form.get("university_roll_no")
            if not university_roll_no:
                return render_template("student_details.html")
            
            # Get 
            student_name = request.form.get("student_name")
            if not student_name:
                return render_template("student_details.html")

            # Get Branch 
            selected_branch = request.form.get("branch_option")
            if not selected_branch:
                return render_template("student_details.html")
            
            # Get Semester
            selected_semester = request.form.get("semester_option")
            if not selected_semester:
                return render_template("student_details.html")
            
            # Get Section
            selected_section = request.form.get("section_option")
            if not selected_section:
                return render_template("student_details.html")
            
            # Get Group
            selected_group = request.form.get("group_option")
            if not selected_group:
                return render_template("student_details.html")
            
            # Get Batch Counselor name
            batch_counselor = request.form.get("batch_counselor")
            if not batch_counselor:
                return render_template("student_details.html")
            
            # If all entries are filled successfuly
            
            # Create student_details table if not there
            # roll no. columns is not unique because if one student makes any mistake
            # that will create hurdles for others
            db.execute(
                "CREATE TABLE IF NOT EXISTS student_details(student_user_id INTEGER PRIMARY KEY NOT NULL, " \
                "university_roll_no TEXT NOT NULL, student_name TEXT NOT NULL, branch TEXT NOT NULL, " \
                "semester INTEGER NOT NULL, section TEXT NOT NULL, class_group TEXT NOT NULL, " \
                "batch_counselor TEXT NOT NULL, FOREIGN KEY (student_user_id) " \
                "REFERENCES students(user_id))"
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

            return redirect("/sodeca_forms") 
         
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
    
    else:
        # Login first
        return redirect("/login")
    
@app.route("/sodeca_forms", methods=["GET", "POST"])
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
def fill_form():

    if session["user_id"]:

        # If not selected any forms, first go and select
        if "selected_forms" not in session:
            flash("Please select atleast one form to submit", "danger")
            return redirect("/sodeca_forms")
        
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
            return redirect("/sodeca_forms")

        # current_form_key is the key coressponding to dict "selected_forms" defined in the start
        current_form = selected_forms[current_form_index]
        form_to_show = FORM_DEFINITIONS[current_form]

        if request.method == "POST":

            # Check if certificate was submitted
            if 'certificate' not in request.files:
                flash("No file part", "danger")
                return redirect(request.url)

            # Dict for text and radio inputs
            form_inputs = {}
            
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

                        # TODO: Error checking using "date_object" 
                        
                        # After succesful parsing only, Append in dict form_inputs
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
                            student_details WHERE student_user_id = ?""", session["user_id"]
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

                        # TODO: Upload certificate to G-Drive

                        # Print file name if saved
                        print(f"File named: {filename} saved successfully!")

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

            # If everything went good
            # Make a list of inputs separated by ","
            form_fields = form_inputs.keys()
            form_fields_sql = ",".join(form_fields)

            # eg. "?,?,?..."
            placeholder_sql = ",".join(["?"]*len(form_inputs))

            # eg. ["Value1", "Value2"...]
            values_list = list(form_inputs.values())

            # eg. "field1 = excluded.field1, field2 = excluded.field2..." 
            update_clause = ", ".join([f"{field} = excluded.{field}" for field in form_fields])

            # Dynamically store form entries in respective tables in database
            db.execute(f"""
                INSERT INTO {current_form} (student_id, {form_fields_sql}, status) 
                VALUES(?, {placeholder_sql}, ?)
                ON CONFLICT(student_id) DO UPDATE SET {update_clause} 
            """, session["user_id"], *values_list, 'pending') # *values_list gives a string eg. "Value1", "Value2"...
            
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
@app.route("/check_submissions", methods=["GET", "POST"])
def check_submissions():
        # On get request
        if request.method == "GET":
            # Show all submissions of a particular batch

            # Empty list to store data from each form in db
            all_forms_data = []

            # Get all forms available in form's definitions
            for form in form_name_list:
                # Get the data for different forms
                form_data = db.execute(f"SELECT * FROM {form}")
                # Append it in list of differnet forms' with data
                all_forms_data.append(form_data)

            return render_template("check_submission.html", forms_data=all_forms_data, form_title_list=form_title, form_names=form_name_list)            

        # On post request
        # Change value of approved or declined in a column
        else:
            return redirect("/sodeca_forms")

@app.route("/update_sheets", methods=["POST"])
def update_sheets():
    flash("Entry updated", "success")
    return redirect(request.url)

@app.route("/blood_donation", methods=["GET", "POST"])
def blood_donation():

    if request.method == "POST":

        # Get the values filled by student
        variables = ["event", "from_date", "to_date", "organizer", "venue", "certificate"]
        form_data = {variable: request.form.get(variable) for variable in variables}

        # TODO: Rename pdf 

        # Store the values directly into csv or maybe sql then csv
        csv_file_path = "blood_donation.csv"

        new_row = [form_data[keys] for keys in variables]

        try:
            with open(csv_file_path, 'a', newline='') as file:
                writer = csv.writer(file)

                # If the file did NOT exist, write the header row first
                if not os.path.exists(csv_file_path):
                    writer.writerow(variables) # writerow for a single row

                # Write the new data row
                writer.writerow(new_row)

        except IOError as e:
            print(f"Error writing to CSV file: {e}")
            return render_template("blood_donation.html")

        return render_template("blood_donation.html")

    else:

        # Fields required in the Form
        fields_required = [
            {"field_name": "Event Title", "field_type": "text", "name": "event", "required": "true"},
            {"field_name": "From Date", "field_type": "date", "name": "from_date", "required": "true"},
            {"field_name": "To Date", "field_type": "date", "name":"to_date", "required": "true"},
            {"field_name": "Organizer", "field_type": "text", "name":"organizer", "required": "true"},
            {"field_name": "Venue", "field_type": "text", "name":"venue", "required": "true"},
            {"field_name": "Certificate / Proof", "field_type": "file", "name":"certificate", 
            "help_text": "Upload your blood donor certificate or equivalent proof", "required": "true"},
            # {"field_name": "I hereby agree", "field_type": "checkbox", "name":"declaration"}
            ]

        return render_template("blood_donation.html", fields=fields_required)

if __name__ == '__main__':

    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    app.run(debug=False)
