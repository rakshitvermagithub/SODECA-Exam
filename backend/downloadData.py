from io import BytesIO

import openpyxl
import os
from flask_session import Session
from cs50 import SQL
from config import Config
from flask import Blueprint, Flask, flash, redirect, render_template, request, session, url_for, jsonify, \
    send_from_directory, \
    make_response, current_app, send_file

app = Flask(__name__)
app.config.from_object(Config)
Session(app)

DATABASE_FILE = app.config["DATABASE_FILE"]
if not os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'w') as f:
            pass

db = SQL(f"sqlite:///{DATABASE_FILE}")

download_bp = Blueprint('download', __name__)

@download_bp.route('/downloadFormData', methods=["POST"])
def downloadFormData():
    if request.method == "POST":
        selected_forms = request.form.getlist("optradio")
        if not selected_forms:
            flash("Please select at least one form to download.", "danger")
            return redirect(request.referrer)
        
        workbook = openpyxl.Workbook()
        default_sheet = workbook.active
        workbook.remove(default_sheet)

        # 1. Map form tables to valid Excel sheet names (OpenPyXL limit is 31 characters)
        form_sheet_names = {
            'blood_donor': "Blood Donor",
            'part_in_comp': "Part in Competition",
            'part_in_work': "Part in Workshop-Seminar",
            'expert_lecture': "Expert Lecture",
            'event_organized': "Organized Event",
            'winner_achievement': "Winner Achievement",
            'internship_stipend': "Internship Stipend",
            'paper_presented': "Paper Presented",
            'financial_grant': "Financial Grant",
            'online_course': "Online Course"
        }

        # 2. Dynamically fetch all columns from student_details (Excluding student_user_id)
        student_col_info = db.execute("SELECT name FROM pragma_table_info('student_details')")        
        student_cols = [c['name'] for c in student_col_info if c['name'] != 'student_user_id']

        # 3. Loop through the forms the admin selected
        for form in selected_forms:
            # Safely create the sheet (fallback to the raw form name, truncated to 31 chars if needed)
            sheet_title = form_sheet_names.get(form, form)[:31]
            sheet = workbook.create_sheet(sheet_title)

            # Dynamically fetch all columns from this specific form
            # Excluding entry_id & student_id (handled manually), and withdrawn_at (per your rules)
            form_col_info = db.execute(f"SELECT name FROM pragma_table_info('{form}')")
            excluded_cols = ['entry_id', 'student_id', 'withdrawn_at', 'certificate', 'full_path']
            form_cols = [c['name'] for c in form_col_info if c['name'] not in excluded_cols]

            # --- BUILD THE HEADER ROW ---
            # Capitalizes and removes underscores (e.g., 'university_roll_no' -> 'University Roll No')
            header = ['Entry ID', 'Student ID'] 
            header += [col.replace('_', ' ').title() for col in student_cols]
            for col in form_cols:
                if col == 'google_file_id':
                    header.append('Proof Drive Link')
                else:
                    header.append(col.replace('_', ' ').title())

            sheet.append(header)

            # --- BUILD THE SQL QUERY STRINGS ---
            # We explicitly define the exact order to match your constraints
            select_items = ["f.entry_id", "f.student_id"]
            select_items.extend([f"s.{c}" for c in student_cols])
            select_items.extend([f"f.{c}" for c in form_cols])
            
            # Combine them into: "f.entry_id, f.student_id, s.name, s.branch, f.topic..."
            select_sql = ", ".join(select_items)

            # --- EXECUTE THE MERGED QUERY ---
            # INNER JOIN merges the profile and form data. 
            # IS NULL perfectly filters out withdrawn entries.
            query = f"""
                SELECT {select_sql}
                FROM {form} f
                INNER JOIN student_details s ON f.student_id = s.student_user_id
                WHERE f.withdrawn_at IS NULL
            """
            rows = db.execute(query)
            
            # --- POPULATE THE EXCEL SHEET ---
            for row in rows:
                row_data = []

                for key, val in row.items():
                    if key == 'google_file_id' and val != 'pending':
                        # Wrap it in Excel's native hyperlink formula
                        formula = f'=HYPERLINK("https://drive.google.com/file/d/{val}/view", "Drive Link")'
                        row_data.append(formula)
                    else:
                        row_data.append(val)

                sheet.append(row_data)

        output = BytesIO()
        workbook.save(output)
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name='SODECA_Batch_Report.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    else:
        return redirect(url_for('/'))