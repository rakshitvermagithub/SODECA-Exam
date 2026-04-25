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
        workbook = openpyxl.Workbook()
        default_sheet = workbook.active
        workbook.remove(default_sheet)

        if 'blood_donor' in selected_forms:
            sheet1 = workbook.create_sheet("1. Blood Donor")
            header1 = ['Entry ID', 'Student ID', 'Event Title',
                       'From Date','To Date','Organizer','Venue',
                       'Certificate / Proof', 'Full Path','Google_file_id',
                       'Status', 'Submitted At','Withdrawn At']
            sheet1.append(header1)
            blood_donor_entries = db.execute("SELECT * FROM blood_donor")
            for item in blood_donor_entries:
                row_data = [item['entry_id'], item['student_id'],
                            item['event_title'], item['from_date'], item['to_date'],
                            item['organizer'],
                            item['venue'], item['certificate'], item['full_path'],
                            item['google_file_id'],
                            item['status'], item['submitted_at'], item['withdrawn_at']]
                sheet1.append(row_data)

        if 'part_in_comp' in selected_forms:
            sheet2 = workbook.create_sheet("2. Participation in Competition or Contest or Activity")
            header2 = ['Entry ID', 'Student ID','Name of the Competition/Event/Activity',
                       'Nature of the Event', 'Team/Individual', 'Event Level',
                       'Event Type','Event Category' ,'Mode of Event', 'From Date','To Date',
                       'Organizer', 'Venue','Certificate/Proof', 'Full Path','Google_file_id',
                       'Status', 'Submitted At','Withdrawn At']
            sheet2.append(header2)
            comp_entries = db.execute("SELECT * FROM part_in_comp")
            for item in comp_entries:
                row_data = [item['entry_id'], item['student_id'],
                            item['event_title'], item['event_nature'], item['participation_type'],
                            item['event_level'], item['event_type'], item['event_category'],
                            item['event_mode'], item['from_date'], item['to_date'],
                            item['organizer'], item['venue'], item['certificate'],
                            item['full_path'], item['google_file_id'],
                            item['status'], item['submitted_at'], item['withdrawn_at']]
                sheet2.append(row_data)

        if 'part_in_work' in selected_forms:
            sheet3 = workbook.create_sheet("3. Workshop or Seminar or Webinar or Conference Attended")
            header3 = ['Entry ID', 'Student ID', 'Event Name',
                       'Event Type', 'Level', 'From Date', 'To Date', 'Mode of Event',
                       'Sponsoring Agency', 'Organized By'
                       'Workshop/Seminar/ Webinar/Conference certificate/proof', 'Full Path','Google_file_id',
                       'Status', 'Submitted At','Withdrawn At']
            sheet3.append(header3)
            work_entries = db.execute("SELECT * FROM part_in_work")
            for item in work_entries:
                row_data = [item['entry_id'], item['student_id'],
                            item['event_title'], item['event_type'], item['event_level'],
                            item['from_date'], item['to_date'], item['mode'],
                            item['sponsor'], item['organizer'], item['certificate'], item['full_path'],
                            item['google_file_id'],
                            item['status'], item['submitted_at'], item['withdrawn_at']]
                sheet3.append(row_data)

        if 'expert_lecture' in selected_forms:
            sheet4 = workbook.create_sheet("4. Expert Lecture Attended")
            header4 = ['Entry ID', 'Student ID', 'Expert Speaker',
                       'Topic','In-house/Away','Mode','From Date',
                       'To Date', 'Organizer', 'Event Venue',
                       'Expert Lecture Attended Certificate/other proof', 'Full Path',
                       'Google_file_id', 'Status', 'Submitted At','Withdrawn At']
            sheet4.append(header4)
            expert_lecture_entries = db.execute("SELECT * FROM expert_lecture")
            for item in expert_lecture_entries:
                row_data = [item['entry_id'], item['student_id'],
                            item['expert_name'], item['topic'], item['location_type'],
                            item['mode'], item['from_date'], item['to_date'], item['organizer'],
                            item['venue'], item['certificate'], item['full_path'],
                            item['google_file_id'],
                            item['status'], item['submitted_at'], item['withdrawn_at']]
                sheet4.append(row_data)

        if 'event_organized' in selected_forms:
            sheet5 = workbook.create_sheet("5. Organized an Event")
            header5 = ['Entry ID', 'Student ID', 'Name of the Event/Activity Organized',
                       'Nature of the Event','Organizing Club/Body','Team/Individual','Event Level',
                       'Event Type', 'Event Category', 'Mode of Event', 'From Date', 'To Date',
                       'Role in event(as mentioned in certificate)', 'No. of Participants in event(approx.)',
                       'Name of Sponsor Agency / Non Sponsored', 'Organizing Institute', 'Event Venue'
                       'Event Organizer Certificate/other proof', 'Full Path','Google_file_id',
                       'Status', 'Submitted At','Withdrawn At']
            sheet5.append(header5)
            event_org_entries = db.execute("SELECT * FROM event_organized")
            for item in event_org_entries:
                row_data = [item['entry_id'], item['student_id'],
                            item['event_name'], item['event_nature'], item['organizing_club'],
                            item['participation_type'], item['event_level'], item['event_type'],
                            item['event_category'], item['mode'], item['from_date'],
                            item['to_date'], item['role'], item['participant_count'], item['sponsor'],
                            item['organizing_institute'],
                            item['venue'], item['certificate'], item['full_path'],
                            item['google_file_id'],
                            item['status'], item['submitted_at'], item['withdrawn_at']]
                sheet5.append(row_data)

        if 'winner_achievement' in selected_forms:
            sheet6 = workbook.create_sheet("6. Winner or Award or Other Achievement")
            header6 = ['Entry ID', 'Student ID', 'Name of the Competition/Event/Activity',
                       'Nature of the Event','Team/Individual','Is it a Hackathon Event?',
                       'Name of the team(If it is Hackathon event)', 'Name of all team members (If it is Hackathon event)',
                       'Position/Place/Rank', 'Other Position/Rank/Title (not mentioned in above list)', 'Award Given (Other than Certificate)',
                       'Cash Prize/Other Prize (if any)', 'Event Level', 'Event Type', 'Event Category', 'Mode of Event',
                       'From Date', 'To Date', 'Date of Receiving Award/Certificate', 'Organized By', 'Event Venue',
                       'Name, Contact, Email Id & Address of Institution/Organization(Event Organizer)',
                       'Name, Contact Email Id & Address of Agency/Body/Organization Giving Award',
                       'Award Certificate/other proof', 'Full Path','Google_file_id',
                       'Status', 'Submitted At','Withdrawn At']
            sheet6.append(header6)
            winner_entries = db.execute("SELECT * FROM winner_achievement")
            for item in winner_entries:
                row_data = [item['entry_id'], item['student_id'],
                            item['event_name'], item['event_nature'], item['participation_type'],
                            item['is_hackathon'], item['team_name'], item['team_members'], item['position'],
                            item['other_position_details'], item['award_type'], item['prize_details'], item['event_level'],
                            item['event_type'], item['event_category'], item['mode'], item['from_date'],
                            item['to_date'], item['award_date'], item['organized_by'],
                            item['venue'], item['organizer_details'], item['award_agency_details'],
                            item['certificate'], item['full_path'], item['google_file_id'],
                            item['status'], item['submitted_at'], item['withdrawn_at']]
                sheet6.append(row_data)

        if 'internship_stipend' in selected_forms:
            sheet7 = workbook.create_sheet("7. Internship or Training (Only with Stipend) before Placement")
            header7 = ['Entry ID', 'Student ID', 'Name of the Company',
                       'Location/Address','Stipend Amount','Stipend Amount Received',
                       'From Date', 'To Date', 'Mode',
                       'Internship/Training Certificate /other proof', 'Full Path','Google_file_id',
                       'Status', 'Submitted At','Withdrawn At']
            sheet7.append(header7)
            internship_entries = db.execute("SELECT * FROM internship_stipend")
            for item in internship_entries:
                row_data = [item['entry_id'], item['student_id'],
                            item['company_name'], item['location'], item['stipend_amount'],
                            item['stipend_frequency'], item['from_date'], item['to_date'],
                            item['mode'], item['certificate'], item['full_path'],
                            item['google_file_id'],
                            item['status'], item['submitted_at'], item['withdrawn_at']]
                sheet7.append(row_data)

        if 'paper_presented' in selected_forms:
            sheet8 = workbook.create_sheet("8. Paper Presented in Conferencer")
            header8 = ['Entry ID', 'Student ID', 'Name of Conference',
                       'National/International','From Date','To Date','Paper Title',
                       'Other Authors (Name, Branch)', 'Mode of Conference', 'Organizer',
                       'Event Venue',
                       'Conference Paper Presented Certificate/other proof', 'Full Path','Google_file_id',
                       'Status', 'Submitted At','Withdrawn At']
            sheet8.append(header8)
            paper_entries = db.execute("SELECT * FROM paper_presented")
            for item in paper_entries:
                row_data = [item['entry_id'], item['student_id'],
                            item['conference_name'], item['conference_level'], item['from_date'], item['to_date'],
                            item['paper_title'], item['other_authors'], item['mode'], item['organizer'],
                            item['venue'], item['certificate'], item['full_path'],
                            item['google_file_id'],
                            item['status'], item['submitted_at'], item['withdrawn_at']]
                sheet8.append(row_data)

        if 'financial_grant' in selected_forms:
            sheet9 = workbook.create_sheet("9. Financial Grant Received")
            header9 = ['Entry ID', 'Student ID', 'Funding Agency Name',
                       'Funded Amount','Funded For','Status of Funding Agency','Funding Date',
                       'Financial Grant Certificate/ other proof', 'Full Path','Google_file_id',
                       'Status', 'Submitted At','Withdrawn At']
            sheet9.append(header9)
            financial_entries = db.execute("SELECT * FROM financial_grant")
            for item in financial_entries:
                row_data = [item['entry_id'], item['student_id'],
                            item['agency_name'], item['funded_amount'], item['funded_for'],
                            item['agency_status'],
                            item['funding_date'], item['certificate'], item['full_path'],
                            item['google_file_id'],
                            item['status'], item['submitted_at'], item['withdrawn_at']]
                sheet9.append(row_data)

        if 'online_course' in selected_forms:
            sheet10 = workbook.create_sheet("10. Coursera or edX Certification")
            header10 = ['Entry ID', 'Student ID', 'Name of the Course',
                       'Platform', 'Date of Completion',
                       'Proof', 'Full Path','Google_file_id',
                       'Status', 'Submitted At','Withdrawn At']
            sheet10.append(header10)
            online_entries = db.execute("SELECT * FROM online_course")
            for item in online_entries:
                row_data = [item['entry_id'], item['student_id'],
                            item['course_name'], item['platform'], item['completion_date'],
                            item['certificate'], item['full_path'],
                            item['google_file_id'],
                            item['status'], item['submitted_at'], item['withdrawn_at']]
                sheet10.append(row_data)

        output = BytesIO()
        workbook.save(output)
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name='report.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    else:
        return redirect(url_for('/'))