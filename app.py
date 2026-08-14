import io

from authlib.integrations.flask_client import OAuth
from cs50 import SQL
from collections import defaultdict

from backend.downloadData import download_bp
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import uuid
# Thread-safe in-memory job tracker
job_status = {}
job_status_lock = threading.Lock()

from config import Config
from datetime import datetime, date, timedelta
from email.message import EmailMessage
from flask import Flask, flash, redirect, render_template, request, session, url_for, jsonify, send_from_directory, \
    make_response, current_app, abort, send_file
from flask_session import Session
from functools import wraps
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from urllib.parse import urlparse, urljoin
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import os
import random
import re
import smtplib
import sys
import pandas as pd
import json
import zipfile

app = Flask(__name__)
app.config.from_object(Config)
Session(app)

app.register_blueprint(download_bp, url_prefix='/download')

app.secret_key = app.config["SECRET_KEY"]

GOOGLE_CLIENT_ID = app.config["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = app.config["GOOGLE_CLIENT_SECRET"]

DRIVE_CLIENT_ID = app.config["DRIVE_CLIENT_ID"]
DRIVE_CLIENT_SECRET = app.config["DRIVE_CLIENT_SECRET"]

SENDER_EMAIL = app.config["SENDER_EMAIL"]
SENDER_PASSWORD = app.config["SENDER_PASSWORD"]

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
MASTER_DRIVE_FOLDER_ID = app.config["MASTER_DRIVE_FOLDER"]

# --- General App Configuration ---
UPLOAD_FOLDER = app.config["UPLOAD_FOLDER"]
if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

DATABASE_FILE = app.config["DATABASE_FILE"]
if not os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'w') as f:
            pass

db = SQL(f"sqlite:///{DATABASE_FILE}")

def login_required(f):
    """
    Decorate routes to require login.
    https://flask.palletsprojects.com/en/3.0.x/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            flash("You are not logged in, login with your SKIT Email ID", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def drive_auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = session.get('drive_auth_token')
        
        if not token:
            # If it's a JSON/fetch request, return JSON error instead of redirect
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return {"error": "drive_auth_required"}, 401
            
            # Original behavior for normal form requests
            flash("Google Drive authorization is missing.", "drive_auth_popup")
            return redirect(request.referrer or '/')
        
        return f(*args, **kwargs)
    return decorated_function
    
def is_safe_url(target):
    """Check if the URL is safe for redirects"""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

def get_folder_id(link):
    # Pattern: looks for "/folders/" followed by the ID chars
    print(f"Link received: {link}")
    match = re.search(r'/folders/([a-zA-Z0-9-_]+)', link)
    
    if match:
        return match.group(1)  # Returns the ID part
    
    # Fallback: Check if the user just pasted the ID directly (no http/https)
    if "http" not in link and len(link) > 20:
        return link.strip()
        
    return None # Invalid link

# Allowed extensions for the certificate upload
ALLOWED_EXTENSIONS = app.config["ALLOWED_EXTENSIONS"]
def allowed_file(filename):
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Form Fields Defined
FORM_DEFINITIONS = {
    'part_in_comp': {
        'title': 'Participation in Competition/Contest/ Activity',
        'description': [
            "Certificate of participation for Cultural / Technical (e.g. Hackathon) / Sports / Non Technical events in any Competition/Contest/Activity organized by SKIT or any other Institute.",
            "It should be a participation certificate for a competition/contest or some significant events",
            "Event should be organized by SKIT or any other institute and you should represent SKIT.",
            "Personal level participation certificate NOT allowed. Only participation in an activity as an SKIT student is valid.",
            "Participation certificate should mention your name as student of SKIT. for e.g. Ajay Gupta of SKIT participated in xyz event.",
            "Certificate of completion (For e.g successfully completed an online assesment/course/training etc) is NOT allowed. Certificate for Appearing in or Clearing an online assesment/test is NOT allowed."
        ],
        'enctype': 'multipart/form-data',
        'fields': [
            {
                'field_label': 'Certification Type',
                'field_type': 'select',
                'field_name': 'certification_type',
                'required': True,
                'options': [
                    {'value': 'participation', 'label': 'Participation'},
                ]
            },
            {
                'field_label': 'Position/Place/Rank',
                'field_type': 'select',
                'field_name': 'position',
                'required': False,
                # Declarative Dependency Schema
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'options': [
                    {'value': 'I', 'label': 'I'},
                    {'value': 'II', 'label': 'II'},
                    {'value': 'III', 'label': 'III'},
                    {'value': 'consolation', 'label': 'Consolation'},
                    {'value': 'other', 'label': 'Other Position/Rank/Title'}
                ]
            },
            {
                'field_label': 'Other Position/Rank/Title (not mentioned in above list)',
                'field_type': 'text',
                'field_name': 'other_position_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': False,
                'placeholder': 'Write NA if position already mentioned',
                'help_text': 'e.g., 28th Rank in National Level Coding Test',
                'field_validation': {'max_length': 150}
            },
            {
                'field_label': 'Award Given (Other than Certificate)',
                'field_type': 'select',
                'field_name': 'award_type',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'options': [
                    {'value': 'medal', 'label': 'Medal'},
                    {'value': 'trophy', 'label': 'Trophy'},
                    {'value': 'cash_prize', 'label': 'Cash Prize'},
                    {'value': 'scholarship', 'label': 'Scholarship'},
                    {'value': 'other', 'label': 'Other Prize'},
                    {'value': 'none', 'label': 'None'}
                ]
            },
            {
                'field_label': 'Cash Prize/Other Prize (if any)',
                'field_type': 'text',
                'field_name': 'prize_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': False,
                'placeholder': 'e.g., Cash Prize of 2000 Rs / T-Shirt',
                'help_text': 'Write NA if no prize',
                'field_validation': {'max_length': 150}
            },
            {
                'field_label': 'Date of Receiving Award/Certificate',
                'field_type': 'date',
                'field_name': 'award_date',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'Name, Contact Email Id & Address of Agency/Body/Organization Giving Award',
                'field_type': 'text',
                'field_name': 'award_agency_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'placeholder': 'e.g., HDFC Bank, Malviya Nagar Branch, ...',
                'field_validation': { 'max_length': 500 }
            },
            {
                'field_label': 'Name of the Competition/Event/Activity',
                'field_type': 'text',
                'field_name': 'event_title',
                'required': True, 
                'placeholder': 'e.g : SUR, Mayukh, Kill With Fire, Game of Quizzes, Mahatma Gandhi Quiz',
                'help_text': 'Exactly as Mentioned in the Certificate',
                'field_validation': {
                    'min_length': 3,
                    'max_length': 50
                }
            },
            {
                'field_label': 'Team/Individual',
                'field_type': 'select',
                'field_name': 'participation_type',
                'required': True,
                'options': [
                    {'value': 'Team', 'label': 'Team'},
                    {'value': 'Individual', 'label': 'Individual'},
                ]
            },
            {
                'field_label': 'Event Category',
                'field_type': 'select',
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
                'field_label': 'Nature of the Event',
                'field_type': 'select',
                'field_name': 'event_nature',
                'required': True,
                'options': [
                    {'value': 'dance', 'label': 'Dance Comp.'},
                    {'value': 'singing', 'label': 'Singing Comp.'},
                    {'value': 'hackathon', 'label': 'Hackathon/ Coding Comp.'},
                    {'value': 'workshop', 'label': 'Workshop/ Seminar/ Webinar/ Symposium'},
                    {'value': 'blood_donor', 'label': 'Blood Donor'},
                    {'value': 'Other', 'label': 'Other'}
                ]
            },
            {
                'field_label': 'Event Level',
                'field_type': 'select',
                'field_name': 'event_level',
                'required': True,
                'help_text': '<b>College Level:</b> Event within SKIT only.<br><b>University Level:</b> Only RTU affiliated college participated.<br><b>State Level:</b> Different colleges/universities all over Rajasthan participated.<br><b>National Level:</b> Colleges/Universities outside Rajasthan participated.<br><b>International Level:</b> Colleges/Universities outside India participated.',
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
                'field_type': 'select',
                'field_name': 'event_type',
                'required': True,
                'options': [
                    {'value': 'Intra College', 'label': 'Intra College'},
                    {'value': 'Inter College', 'label': 'Inter College'},
                ]
            },
            {
                'field_label': 'Mode of Event',
                'field_type': 'select',
                'field_name': 'event_mode',
                'required': True,
                'options': [
                    {'value': 'Online', 'label': 'Online'},
                    {'value': 'Offline', 'label': 'Offline'},
                ]
            },
            {
                'field_label': 'From Date',
                'field_type': 'date',
                'field_name': 'from_date',
                'required': True,
                'help_text': 'Start date of the event',
                'field_validation': {
                    'max_date': 'today'
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
                    'after_field': 'from_date'
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
                'help_text': 'Location where the event took place. Write "Online Activity" if event mode was online',
                'field_validation': {
                    'min_length': 3,
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
                    'accepted_types': '.pdf',
                    'max_size': '5MB'
                }
            }
        ]
    },

    'winner_achievement': {
        'title': 'Winner/Award/ Other Achievement',
        'description':[
            'Winner/Runner Up/ Consolation/Good Rank or Position/award/prize in some high level Cultural/Technical(e.g. Hackathon)/ Sports/Non Technical competition/contest organized by SKIT or any other Institute/university/organization.',
            'For e.g. Winner in Inter College Singing Competition/ Hackathon Runner Up/ 3rd Position in quiz competition/ 450 Rank in international level coding test such as google code Jam / Player of the tournament award in state level cricket league etc'
            'Certificate should mention some Rank/Place/Position in a competition or some high level achievement like man of the match/player of the tournament etc.'
            'Non Competition certificates for e.g. Certificate of clearing some exam/test/assessment(with some score) but without a rank/position/place is NOT allowed. It should be a certificate for only a "competition/contest" activity.'
            ],
        'enctype': 'multipart/form-data',
        'fields': [
            {
                'field_label': 'Certification Type',
                'field_type': 'select',
                'field_name': 'certification_type',
                'required': True,
                'options': [
                    {'value': 'achievement', 'label': 'Achievement'}
                ]
            },
            {
                'field_label': 'Position/Place/Rank',
                'field_type': 'select',
                'field_name': 'position',
                'required': False,
                # Declarative Dependency Schema
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'options': [
                    {'value': 'I', 'label': 'I'},
                    {'value': 'II', 'label': 'II'},
                    {'value': 'III', 'label': 'III'},
                    {'value': 'consolation', 'label': 'Consolation'},
                    {'value': 'other', 'label': 'Other Position/Rank/Title'}
                ]
            },
            {
                'field_label': 'Other Position/Rank/Title (not mentioned in above list)',
                'field_type': 'text',
                'field_name': 'other_position_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': False,
                'placeholder': 'Write NA if position already mentioned',
                'help_text': 'e.g., 28th Rank in National Level Coding Test',
                'field_validation': {'max_length': 150}
            },
            {
                'field_label': 'Award Given (Other than Certificate)',
                'field_type': 'select',
                'field_name': 'award_type',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'options': [
                    {'value': 'medal', 'label': 'Medal'},
                    {'value': 'trophy', 'label': 'Trophy'},
                    {'value': 'cash_prize', 'label': 'Cash Prize'},
                    {'value': 'scholarship', 'label': 'Scholarship'},
                    {'value': 'other', 'label': 'Other Prize'},
                    {'value': 'none', 'label': 'None'}
                ]
            },
            {
                'field_label': 'Cash Prize/Other Prize (if any)',
                'field_type': 'text',
                'field_name': 'prize_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': False,
                'placeholder': 'e.g., Cash Prize of 2000 Rs / T-Shirt',
                'help_text': 'Write NA if no prize',
                'field_validation': {'max_length': 150}
            },
            {
                'field_label': 'Date of Receiving Award/Certificate',
                'field_type': 'date',
                'field_name': 'award_date',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'Name, Contact Email Id & Address of Agency/Body/Organization Giving Award',
                'field_type': 'text',
                'field_name': 'award_agency_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'placeholder': 'e.g., HDFC Bank, Malviya Nagar Branch, ...',
                'field_validation': { 'max_length': 500 }
            },
            {
                'field_label': 'Name of the Competition/Event/Activity',
                'field_type': 'text',
                'field_name': 'event_name',
                'required': True,
                'placeholder': 'e.g., Google Code Jam, Smart India Hackathon',
                'help_text': 'Exactly as Mentioned in the Certificate.',
                'field_validation': { 'max_length': 150 }
            },
            {
                'field_label': 'Event Category',
                'field_type': 'select',
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
                'field_label': 'Nature of the Event',
                'field_type': 'select',
                'field_name': 'event_nature',
                'required': True,
                'options': [
                    {'value': 'dance', 'label': 'Dance Comp.'},
                    {'value': 'singing', 'label': 'Singing Comp.'},
                    {'value': 'hackathon', 'label': 'Hackathon/ Coding Comp.'},
                    {'value': 'workshop', 'label': 'Workshop/ Seminar/ Webinar/ Symposium'},
                    {'value': 'blood_donor', 'label': 'Blood Donor'},
                    {'value': 'Other', 'label': 'Other'}
                ]
            },
            {
                'field_label': 'Event Level',
                'field_type': 'select',
                'field_name': 'event_level',
                'required': True,
                'help_text': '<b>College Level:</b> Event within SKIT only.<br><b>University Level:</b> Only RTU affiliated college participated.<br><b>State Level:</b> Different colleges/universities all over Rajasthan participated.<br><b>National Level:</b> Colleges/Universities outside Rajasthan participated.<br><b>International Level:</b> Colleges/Universities outside India participated.',
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
                'field_type': 'select',
                'field_name': 'event_type',
                'required': True,
                'options': [
                    {'value': 'Intra College', 'label': 'Intra College'},
                    {'value': 'Inter College', 'label': 'Inter College'},
                ]
            },
            {
                'field_label': 'Team/Individual',
                'field_type': 'select',
                'field_name': 'team_individual',
                'required': True,
                'options': [
                    {'value': 'individual', 'label': 'Individual'},
                    {'value': 'team', 'label': 'Team'}
                ]
            },
            {
                'field_label': 'Name of the team(If it is Hackathon event)',
                'field_type': 'text',
                'field_name': 'team_name',
                'required': False,
                'depends_on': {
                    'field': 'team_individual',
                    'value': 'team'
                },
                'required_if_visible': True,
                'placeholder': 'Write NA if not a Hackathon event',
                'field_validation': { 'max_length': 100 }
            },
            {
                'field_label': 'Name of all team members (If it is Hackathon event)',
                'field_type': 'text',
                'field_name': 'team_members',
                'required': False,
                'depends_on': {
                    'field': 'team_individual',
                    'value': 'team'
                },
                'required_if_visible': True,
                'placeholder': 'Write NA if not a Hackathon event',
                'field_validation': { 'max_length': 500 }
            },
            {
                'field_label': 'Mode of Event',
                'field_type': 'select',
                'field_name': 'event_mode',
                'required': True,
                'options': [
                    {'value': 'Online', 'label': 'Online'},
                    {'value': 'Offline', 'label': 'Offline'},
                ]
            },
            {
                'field_label': 'From Date',
                'field_type': 'date',
                'field_name': 'from_date',
                'required': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'To Date',
                'field_type': 'date',
                'field_name': 'to_date',
                'required': True,
                'field_validation': { 
                    'max_date': 'today',                     
                    'after_field': 'from_date'  # Must be after from_date
                }
            },
            {
                'field_label': 'Name, Contact, Email Id & Address of Institution/Organization(Event Organizer)',
                'field_type': 'text',
                'field_name': 'organizer_details',
                'required': True,
                'placeholder': 'e.g., SKIT Jaipur, info@skit.ac.in, ...',
                'field_validation': { 'max_length': 500 }
            },
            {
                'field_label': 'Event Venue',
                'field_type': 'text',
                'field_name': 'venue',
                'required': True,
                'placeholder': 'e.g., SKIT Jaipur / Write online if online',
                'field_validation': { 'min_length': 3, 'max_length': 200 }
            },
            {
                'field_label': 'Award Certificate/other proof',
                'field_type': 'file',
                'field_name': 'certificate',
                'required': True,
                'help_text': 'Only PDF file format is acceptable. Max Size: 5MB',
                'validation': { 'accepted_types': '.pdf', 'max_size': '5MB' }
            }
        ]
    },

    'online_course': {
        'title': 'Coursera / edX Certification',
        'description': [
            "Only Upload Coursera/edX Certificates. Course certificates from other platforms such as Udemy are NOT allowed."
        ],
        'enctype': 'multipart/form-data',
        'fields': [
            {
                'field_label': 'Certification Type',
                'field_type': 'select',
                'field_name': 'certification_type',
                'required': True,
                'options': [
                    {'value': 'participation', 'label': 'Participation'},
                    {'value': 'achievement', 'label': 'Achievement'}
                ]
            },
            {
                'field_label': 'Position/Place/Rank',
                'field_type': 'select',
                'field_name': 'position',
                'required': False,
                # Declarative Dependency Schema
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'options': [
                    {'value': 'I', 'label': 'I'},
                    {'value': 'II', 'label': 'II'},
                    {'value': 'III', 'label': 'III'},
                    {'value': 'consolation', 'label': 'Consolation'},
                    {'value': 'other', 'label': 'Other Position/Rank/Title'}
                ]
            },
            {
                'field_label': 'Other Position/Rank/Title (not mentioned in above list)',
                'field_type': 'text',
                'field_name': 'other_position_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': False,
                'placeholder': 'Write NA if position already mentioned',
                'help_text': 'e.g., 28th Rank in National Level Coding Test',
                'field_validation': {'max_length': 150}
            },
            {
                'field_label': 'Award Given (Other than Certificate)',
                'field_type': 'select',
                'field_name': 'award_type',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'options': [
                    {'value': 'medal', 'label': 'Medal'},
                    {'value': 'trophy', 'label': 'Trophy'},
                    {'value': 'cash_prize', 'label': 'Cash Prize'},
                    {'value': 'scholarship', 'label': 'Scholarship'},
                    {'value': 'other', 'label': 'Other Prize'},
                    {'value': 'none', 'label': 'None'}
                ]
            },
            {
                'field_label': 'Cash Prize/Other Prize (if any)',
                'field_type': 'text',
                'field_name': 'prize_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': False,
                'placeholder': 'e.g., Cash Prize of 2000 Rs / T-Shirt',
                'help_text': 'Write NA if no prize',
                'field_validation': {'max_length': 150}
            },
            {
                'field_label': 'Date of Receiving Award/Certificate',
                'field_type': 'date',
                'field_name': 'award_date',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'Name, Contact Email Id & Address of Agency/Body/Organization Giving Award',
                'field_type': 'text',
                'field_name': 'award_agency_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'placeholder': 'e.g., HDFC Bank, Malviya Nagar Branch, ...',
                'field_validation': { 'max_length': 500 }
            },
            {
                'field_label': 'Name of the Course',
                'field_type': 'text',
                'field_name': 'course_name',
                'required': True,
                'placeholder': 'e.g., Python for Everybody',
                'field_validation': { 'max_length': 150 }
            },
            {
                'field_label': 'Platform',
                'field_type': 'text',
                'field_name': 'platform',
                'required': True,
                'placeholder': 'e.g., Coursera, edX, Udemy',
                'field_validation': { 'max_length': 100 }
            },
            {
                'field_label': 'Date of Completion',
                'field_type': 'date',
                'field_name': 'completion_date',
                'required': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'Proof',
                'field_type': 'file',
                'field_name': 'certificate',
                'required': True,
                'help_text': 'Only PDF file format is acceptable. Max Size: 5MB',
                'validation': {
                    'accepted_types': '.pdf',
                    'max_size': '5MB'
                }
            }
        ]
    },
    
    'internship_stipend': {
        'title': 'Internship/Training (Only with Stipend) before Placement',
        'description': [
            'Submit details for a paid internship or training that occurred before any final job placement.'
        ],
        'enctype': 'multipart/form-data',
        'fields': [
            {
                'field_label': 'Certification Type',
                'field_type': 'select',
                'field_name': 'certification_type',
                'required': True,
                'options': [
                    {'value': 'participation', 'label': 'Participation'},
                    {'value': 'achievement', 'label': 'Achievement'}
                ]
            },
            {
                'field_label': 'Position/Place/Rank',
                'field_type': 'select',
                'field_name': 'position',
                'required': False,
                # Declarative Dependency Schema
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'options': [
                    {'value': 'I', 'label': 'I'},
                    {'value': 'II', 'label': 'II'},
                    {'value': 'III', 'label': 'III'},
                    {'value': 'consolation', 'label': 'Consolation'},
                    {'value': 'other', 'label': 'Other Position/Rank/Title'}
                ]
            },
            {
                'field_label': 'Other Position/Rank/Title (not mentioned in above list)',
                'field_type': 'text',
                'field_name': 'other_position_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': False,
                'placeholder': 'Write NA if position already mentioned',
                'help_text': 'e.g., 28th Rank in National Level Coding Test',
                'field_validation': {'max_length': 150}
            },
            {
                'field_label': 'Award Given (Other than Certificate)',
                'field_type': 'select',
                'field_name': 'award_type',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'options': [
                    {'value': 'medal', 'label': 'Medal'},
                    {'value': 'trophy', 'label': 'Trophy'},
                    {'value': 'cash_prize', 'label': 'Cash Prize'},
                    {'value': 'scholarship', 'label': 'Scholarship'},
                    {'value': 'other', 'label': 'Other Prize'},
                    {'value': 'none', 'label': 'None'}
                ]
            },
            {
                'field_label': 'Cash Prize/Other Prize (if any)',
                'field_type': 'text',
                'field_name': 'prize_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': False,
                'placeholder': 'e.g., Cash Prize of 2000 Rs / T-Shirt',
                'help_text': 'Write NA if no prize',
                'field_validation': {'max_length': 150}
            },
            {
                'field_label': 'Date of Receiving Award/Certificate',
                'field_type': 'date',
                'field_name': 'award_date',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'Name, Contact Email Id & Address of Agency/Body/Organization Giving Award',
                'field_type': 'text',
                'field_name': 'award_agency_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'placeholder': 'e.g., HDFC Bank, Malviya Nagar Branch, ...',
                'field_validation': { 'max_length': 500 }
            },
            {
                'field_label': 'Name of the Company',
                'field_type': 'text',
                'field_name': 'company_name',
                'required': True,
                'placeholder': 'e.g., Google, Microsoft, Amazon',
                'help_text': 'The internship/training should be done before the student is placed in a company and got stipend.',
                'field_validation': { 'max_length': 150 }
            },
            {
                'field_label': 'Location/Address',
                'field_type': 'text',
                'field_name': 'location',
                'required': True,
                'placeholder': 'e.g., Bengaluru, Karnataka. Write "Online" if mode was online',
                'field_validation': { 'min_length': 5, 'max_length': 300 }
            },
            {
                'field_label': 'Stipend Amount',
                'field_type': 'number',
                'field_name': 'stipend_amount',
                'required': True,
                'placeholder': 'e.g. 5000',
                'help_text': 'Enter the numeric value of the stipend in Rs. Do NOT include commas or currency symbols.',
                'field_validation': { 'min': 1 }
            },
            {
                'field_label': 'Stipend Amount Received',
                'field_type': 'radio',
                'field_name': 'stipend_frequency',
                'required': True,
                'options': [
                    {'value': 'per_month', 'label': 'Per Month'},
                    {'value': 'lump_sum', 'label': 'Lump Sum'}
                ]
            },
            {
                'field_label': 'From Date',
                'field_type': 'date',
                'field_name': 'from_date',
                'required': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'To Date',
                'field_type': 'date',
                'field_name': 'to_date',
                'required': True,
                'field_validation': { 'max_date': 'today', 'after_field': 'from_date' }
            },
            {
                'field_label': 'Mode',
                'field_type': 'radio',
                'field_name': 'mode',
                'required': True,
                'options': [
                    {'value': 'online', 'label': 'Online'},
                    {'value': 'offline', 'label': 'Offline'}
                ]
            },
            {
                'field_label': 'Internship/Training Certificate /other proof',
                'field_type': 'file',
                'field_name': 'certificate',
                'required': True,
                'help_text': '''Certificate must contain proof of stipend. If not, merge proof (bank statement, offer letter) into the PDF.
                Max Size: 10MB''',
                'validation': {
                    'accepted_types': '.pdf',
                    'max_size': '10MB'
                }
            }
        ]
    },

    'paper_presented': {
        'title': 'Paper Presented in Conference',
        'description': [
            "Presented paper in any conference (National/International) at SKIT or outside SKIT",
        ],
        'enctype': 'multipart/form-data',
        'fields': [
            {
                'field_label': 'Certification Type',
                'field_type': 'select',
                'field_name': 'certification_type',
                'required': True,
                'options': [
                    {'value': 'participation', 'label': 'Participation'},
                    {'value': 'achievement', 'label': 'Achievement'}
                ]
            },
            {
                'field_label': 'Position/Place/Rank',
                'field_type': 'select',
                'field_name': 'position',
                'required': False,
                # Declarative Dependency Schema
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'options': [
                    {'value': 'I', 'label': 'I'},
                    {'value': 'II', 'label': 'II'},
                    {'value': 'III', 'label': 'III'},
                    {'value': 'consolation', 'label': 'Consolation'},
                    {'value': 'other', 'label': 'Other Position/Rank/Title'}
                ]
            },
            {
                'field_label': 'Other Position/Rank/Title (not mentioned in above list)',
                'field_type': 'text',
                'field_name': 'other_position_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': False,
                'placeholder': 'Write NA if position already mentioned',
                'help_text': 'e.g., 28th Rank in National Level Coding Test',
                'field_validation': {'max_length': 150}
            },
            {
                'field_label': 'Award Given (Other than Certificate)',
                'field_type': 'select',
                'field_name': 'award_type',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'options': [
                    {'value': 'medal', 'label': 'Medal'},
                    {'value': 'trophy', 'label': 'Trophy'},
                    {'value': 'cash_prize', 'label': 'Cash Prize'},
                    {'value': 'scholarship', 'label': 'Scholarship'},
                    {'value': 'other', 'label': 'Other Prize'},
                    {'value': 'none', 'label': 'None'}
                ]
            },
            {
                'field_label': 'Cash Prize/Other Prize (if any)',
                'field_type': 'text',
                'field_name': 'prize_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': False,
                'placeholder': 'e.g., Cash Prize of 2000 Rs / T-Shirt',
                'help_text': 'Write NA if no prize',
                'field_validation': {'max_length': 150}
            },
            {
                'field_label': 'Date of Receiving Award/Certificate',
                'field_type': 'date',
                'field_name': 'award_date',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'Name, Contact Email Id & Address of Agency/Body/Organization Giving Award',
                'field_type': 'text',
                'field_name': 'award_agency_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'placeholder': 'e.g., HDFC Bank, Malviya Nagar Branch, ...',
                'field_validation': { 'max_length': 500 }
            },
            {
                'field_label': 'Name of Conference',
                'field_type': 'text',
                'field_name': 'conference_name',
                'required': True,
                'placeholder': 'e.g., 3rd International Conference on Internet of Things...',
                'field_validation': { 'max_length': 200 }
            },
            {
                'field_label': 'National/International',
                'field_type': 'radio',
                'field_name': 'conference_level',
                'required': True,
                'options': [
                    {'value': 'national', 'label': 'National'},
                    {'value': 'international', 'label': 'International'}
                ]
            },
            {
                'field_label': 'From Date',
                'field_type': 'date',
                'field_name': 'from_date',
                'required': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'To Date',
                'field_type': 'date',
                'field_name': 'to_date',
                'required': True,
                'field_validation': { 'max_date': 'today', 'after_field': 'from_date' }
            },
            {
                'field_label': 'Paper Title',
                'field_type': 'text',
                'field_name': 'paper_title',
                'required': True,
                'placeholder': 'Enter the full title of your paper',
                'field_validation': { 'max_length': 250 }
            },
            {
                'field_label': 'Other Authors (Name, Branch)',
                'field_type': 'text',
                'field_name': 'other_authors',
                'required': True,
                'placeholder': 'e.g., 1. Ajay Sharma, CSE 2. Abhay Kumar, CSE.',
                'field_validation': { 'max_length': 500 }
            },
            {
                'field_label': 'Mode of Conference',
                'field_type': 'radio',
                'field_name': 'mode',
                'required': True,
                'options': [
                    {'value': 'online', 'label': 'Online'},
                    {'value': 'offline', 'label': 'Offline'}
                ]
            },
            {
                'field_label': 'Organizer',
                'field_type': 'text',
                'field_name': 'organizer',
                'required': True,
                'placeholder': 'e.g., IEEE, Springer, SKIT Jaipur',
                'field_validation': { 'max_length': 150 }
            },
            {
                'field_label': 'Event Venue',
                'field_type': 'text',
                'field_name': 'venue',
                'required': True,
                'placeholder': 'e.g., SKIT Jaipur / Write online if online',
                'field_validation': { 'min_length': 3, 'max_length': 200 }
            },
            {
                'field_label': 'Conference Paper Presented Certificate/other proof',
                'field_type': 'file',
                'field_name': 'certificate',
                'required': True,
                'help_text': 'Proof for paper presentation is mandatory. Max Size: 5MB',
                'validation': {
                    'accepted_types': '.pdf',
                    'max_size': '5MB'
                }
            }
        ]
    },

    'financial_grant': {
        'title': 'Financial Grant Received',
        'description': [
            "Received any financial funding for project/start up/DST project etc. from private/government agency."
        ],
        'enctype': 'multipart/form-data',
        'fields': [
            {
                'field_label': 'Funding Agency Name',
                'field_type': 'text',
                'field_name': 'agency_name',
                'required': True,
                'placeholder': 'e.g., Department of Science & Technology, Govt. of India',
                'field_validation': { 'max_length': 200 }
            },
            {
                'field_label': 'Funded Amount',
                'field_type': 'number',
                'field_name': 'funded_amount',
                'required': True,
                'placeholder': 'Enter the amount in Rs.',
                'field_validation': { 'min': 1 }
            },
            {
                'field_label': 'Funded For',
                'field_type': 'text',
                'field_name': 'funded_for',
                'required': True,
                'placeholder': 'e.g., Research Project, Startup Idea, Conference Travel',
                'field_validation': { 'max_length': 250 }
            },
            {
                'field_label': 'Status of Funding Agency',
                'field_type': 'radio',
                'field_name': 'agency_status',
                'required': True,
                'options': [
                    {'value': 'private', 'label': 'Private'},
                    {'value': 'government', 'label': 'Government'}
                ]
            },
            {
                'field_label': 'Funding Date',
                'field_type': 'date',
                'field_name': 'funding_date',
                'required': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'Financial Grant Certificate/ other proof',
                'field_type': 'file',
                'field_name': 'certificate',
                'required': True,
                'help_text': 'Only PDF file format is acceptable. Max Size: 5MB',
                'validation': {
                    'accepted_types': '.pdf',
                    'max_size': '5MB'
                }
            }
        ]
    }
}

# List of technical names of forms defined(SQL Names)
form_name_list = list(FORM_DEFINITIONS.keys())

# Create tables for all the forms in FORM_DEFINITIONS
for form in form_name_list:
    # Check if table named the form exists
    # db.execute(f"DROP TABLE {form}")
    table_exists = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", form)

    # If not exists
    if not table_exists:

        # List to store differnet fields definition
        col_def_list = []
        for field_col in FORM_DEFINITIONS[form]["fields"]:

            field_col_name = field_col["field_name"]

            # Defining form fields with dataype TEXT and is REQUIRED
            if field_col["required"] == False:
                    col_def = f"{field_col_name} TEXT NOT NULL DEFAULT 'NA'"
            else:
                col_def = f"{field_col_name} TEXT NOT NULL"

            col_def_list.append(col_def)

        # SQL string
        field_cols_sql = ",".join(col_def_list)

        # Dynamically create SQL tables for all forms
        db.execute(
            f"""CREATE TABLE IF NOT EXISTS {form}(
            entry_id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            student_id INTEGER NOT NULL,
            sem INTEGER NOT NULL,
            branch TEXT NOT NULL,
            section TEXT NOT NULL,
            academic_session TEXT,
            academic_term TEXT,
            {field_cols_sql},
            full_path TEXT NOT NULL,
            google_file_id TEXT NOT NULL DEFAULT 'pending',
            status TEXT DEFAULT 'pending' NOT NULL,
            submitted_at TIMESTAMP NOT NULL DEFAULT (datetime('now', '+5 hours', '+30 minutes')),
            withdrawn_at TIMESTAMP, rejection_note TEXT,
            FOREIGN KEY (student_id) REFERENCES student_details(student_user_id),
            CHECK (status IN ('pending', 'accepted', 'rejected'))
            )"""
        )

# List of title names of forms defined
form_title = []
form_values = []
form_label = []
for form in FORM_DEFINITIONS:

    query = f"SELECT * FROM {form}"
    form_values.append(db.execute(query))
    form_title.append(FORM_DEFINITIONS[form]["title"])

# form name and title dictionary
form_dict = dict(zip(form_name_list, form_title))

# Initialise table to store user login details
db.execute("""
    CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    email TEXT UNIQUE NOT NULL, hash_password TEXT, google_id TEXT UNIQUE,
    auth_provider TEXT DEFAULT 'local' NOT NULL, profile_picture TEXT,
    first_name TEXT, last_name TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, role TEXT NOT NULL DEFAULT 'student'
    CHECK (role IN ('student', 'faculty', 'coordinator', 'admin')))
""")
# Initialise table to store student details
db.execute("""
    CREATE TABLE IF NOT EXISTS student_details(student_user_id INTEGER PRIMARY KEY NOT NULL,
    university_roll_no TEXT NOT NULL, student_name TEXT NOT NULL, branch TEXT NOT NULL,
    semester INTEGER NOT NULL, section TEXT NOT NULL, batch_counselor TEXT, 
    FOREIGN KEY (student_user_id) REFERENCES users(user_id) ON DELETE CASCADE)
""")
# Initialise table to store faculty details
db.execute("""
    CREATE TABLE IF NOT EXISTS faculty_details(college_email TEXT PRIMARY KEY NOT NULL,
    faculty_user_id INTEGER UNIQUE, full_name TEXT NOT NULL, designation TEXT NOT NULL,
    department TEXT NOT NULL, semester INTEGER, branch TEXT, section TEXT, 
    contact TEXT NOT NULL DEFAULT 'to be updated',
    is_coordinator INTEGER DEFAULT 0,
    FOREIGN KEY (faculty_user_id) REFERENCES users(user_id))
    """)

# Create a table to store and map drive folder ids
db.execute("""
    CREATE TABLE IF NOT EXISTS drive_folder_map (id TEXT PRIMARY KEY NOT NULL,
    drive_folder_id TEXT UNIQUE NOT NULL, branch TEXT NOT NULL, 
    semester TEXT NOT NULL, section TEXT NOT NULL, 
    form_name TEXT NOT NULL) 
    """)
# Create a table to store sodeca drive master folder link and academic session
db.execute("""
    CREATE TABLE IF NOT EXISTS drive_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        master_folder_link TEXT, master_folder_id TEXT,
        participation_folder_link TEXT, participation_folder_id TEXT,
        achievement_folder_link TEXT, achievement_folder_id TEXT,
        academic_session TEXT, academic_term TEXT,
        updated_on TIMESTAMP NOT NULL DEFAULT (datetime('now', '+5 hours', '+30 minutes')) 
    ) 
""")

db.execute("""
    CREATE TABLE IF NOT EXISTS batch_structure (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sem INTEGER, 
        branch TEXT,
        section TEXT,
        academic_session TEXT,
        academic_term TEXT,
        updated_on TIMESTAMP NOT NULL DEFAULT (datetime('now', '+5 hours', '+30 minutes')) 
    ) 
""")

db.execute("""
    CREATE TABLE IF NOT EXISTS batch_structure_summary (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        sem_list TEXT,
        branch_list TEXT,
        updated_on TIMESTAMP NOT NULL DEFAULT (datetime('now', '+5 hours', '+30 minutes'))
    )
""")

# Dictionary containing folder names of different semesters
semester_dict = {"1": "I Semester", "2": "II Semester", "3": "III Semester",
             "4": "IV Semester", "5": "V Semester", "6": "VI Semester",
             "7": "VII Semester", "8": "VIII Semester"}

# Define the users to insert (using the @skit.ac.in domain)
demoUsers = [
    {
        "email": "student@skit.ac.in",
        "password": "student123",
        "role": "student"
    },
    {
        "email": "faculty@skit.ac.in",
        "password": "faculty123",
        "role": "faculty"
    },
    {
        "email": "admin@skit.ac.in",
        "password": "admin123",
        "role": "admin"
    }
]

# Generate and print the SQL insert statements
# for user in demoUsers:
#     hashed_pw = generate_password_hash(user["password"])
#     sql = f"""INSERT INTO users (email, hash_password, role) 
# VALUES ('{user["email"]}', '{hashed_pw}', '{user["role"]}');"""
#     db.execute(sql)

def get_or_create_folder(service, folder_name, parent_id=None):
    """
    Searches for a specific folder inside a parent folder.
    If it exists, returns its ID. If not, creates it and returns the new ID.
    """
    try:
        # 1. Search Query: Find folders with this specific name inside the parent
        query_parts = [
                    "mimeType = 'application/vnd.google-apps.folder'",
                    f"name = '{folder_name}'",
                    "trashed = false"
                ]
                
        if parent_id:
            query_parts.append(f"'{parent_id}' in parents")
        
        query = " and ".join(query_parts)    

        results = service.files().list(
            q=query, 
            spaces='drive', 
            fields='files(id, name)'
        ).execute()
        
        files = results.get('files', [])

        if files:
            # Found it! Return the existing ID
            print(f"Found existing folder: {folder_name} ({files[0]['id']})")
            flash(f"Found existing folder: {folder_name}")
            return files[0]['id']
        else:
            # Not found. Create it!
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
            }

            if parent_id:
                file_metadata['parents'] = [parent_id]

            folder = service.files().create(
                body=file_metadata, 
                fields='id'
            ).execute()
            print(f"Created new folder: {folder_name} ({folder.get('id')})")
            return folder.get('id')

    except Exception as e:
        print(f"Error in get_or_create_folder: {e}")
        return None

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

# Returns the current time in Jaipur/India (IST) formatted as a string.
def get_current_ist_time():
    # IST is UTC + 5:30
    ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    return ist_now.strftime("%Y-%m-%d %I:%M:%S %p")

# Get list of faculty emails
faculty_emails = []
def update_faculty_emails():
    faculty_dict = db.execute("SELECT college_email FROM faculty_details")
    for faculty in faculty_dict:
        faculty_emails.append(faculty["college_email"])

# Get list of developer emails
# dev_emails = []
# def update_dev_emails():
#     dev_dict = db.execute("SELECT email FROM users WHERE role='dev'")
#     for dev in dev_dict:
#         dev_emails.append(dev["email"])

def check_dev_email(email):

    devs = db.execute("SELECT email FROM users WHERE role='dev'")

    for dev in devs:
        print(f"Comparing {dev["email"]}, {email}")
        if dev["email"] == email:
            print(f"Comparing {dev["email"]}, {email}")
            return True
        
    return False

# Send otp when to users registering manually(without google sign-in)
def send_otp(to_mail):
    if not to_mail:
        return "Error!, Email not found in the session.", 400

    otp = ""
    for _ in range(6):
        otp += str(random.randint(0, 9))

    session['otp_email'] = to_mail
    session['otp_secret'] = otp
    print(otp)

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(SENDER_EMAIL, SENDER_PASSWORD)

    msg = EmailMessage()
    msg['Subject'] = "OTP Verification"
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_mail
    msg.set_content("OTP to register your account is: " + otp)

    server.send_message(msg)
    server.quit()

@app.route("/download/<pk>")
def download(pk):
    result_instance = db.execute(
        "SELECT student_details.*,users.email FROM student_details INNER JOIN users ON student_details.student_user_id = users.user_id"
    )
    print(result_instance)
    emails = db.execute(
        "SELECT email FROM users WHERE role = 'student'"
    )
    if len(result_instance) > 0:
        # Add Email column also
        data = [
            {
                'Name': result["student_name"],
                'Roll No': result["university_roll_no"],
                'Email': result["email"],
                'Branch': result["branch"],
                'Semester': result["semester"],
                'Section': result["section"],
                'Batch Counselor': result["batch_counselor"]
            }
            for result in result_instance
        ]
    else:
        data = [
            {
                'Email': email["email"]
            }
            for email in emails
        ]

    df = pd.DataFrame(data)
    if pk == "excel_stu_dir":
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='openpyxl')
        df.to_excel(writer, index=False, sheet_name="student_directory")
        writer.close()
        excel_data = output.getvalue()
        response = make_response(excel_data)
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Content-Disposition'] = 'attachment; filename="student_directory.xlsx"'
        return response

    elif pk == "csv_stu_dir":
        output = io.StringIO()
        df.to_csv(output, index=False)
        csv_string = output.getvalue()

        return make_response(
            csv_string,
            {
                "Content-Type": "text/csv",
                "Content-Disposition": "attachment; filename=student_directory.csv"
            }
        )

# Admin setup route
@app.route("/setup", methods=["GET", "POST"])
def setup():
    # Check if any admin already exists in the database. 
    # If even one exists, this route should be disabled.
    admin_check = db.execute("SELECT user_id FROM users WHERE role = 'admin' LIMIT 1")
    
    if admin_check:
        flash("System is already initialized. Please login.", "info")
        return redirect(url_for("login"))

    if request.method == "POST":
        # Collect form data
        email = request.form.get("admin_email")
        password = request.form.get("admin_password")
        confirm = request.form.get("confirm_password")

        # Backend Validation (Security Best Practice)
        if not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("setup"))

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("setup"))

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "danger")
            return redirect(url_for("setup"))

        # Hash the password
        hash_password = generate_password_hash(password)

        try:
            # Store in database
            # We explicitly set 'role' to 'admin'
            db.execute("""
                INSERT INTO users (email, hash_password, role) 
                VALUES (?, ?, 'admin')
            """, email, hash_password)

            flash("System initialized successfully! You can now log in as Admin.", "success")
            return redirect(url_for("login"))

        except Exception as e:
            # Handle cases like the email already being in use
            flash("An error occurred during setup. Perhaps this email is already registered?", "danger")
            print(f"Setup Error: {e}")
            return redirect(url_for("setup"))

    # GET request: Show the initialization form
    return render_template("setup.html")

# Homepage route
@app.route("/", methods=["GET"])
def sodeca_home():
    # If admin
    if session.get("user_role") == 'admin':
        return redirect(url_for("super_admin"))
    # If faculty
    elif session.get("user_role") == 'faculty':
        return redirect(url_for("faculty_dashboard"))
    # If coordinator
    elif session.get("user_role") == 'coordinator':
        return redirect(url_for("coordinator"))
    # If student
    return render_template("sodeca_home.html")

# Register
@app.route("/register", methods=["GET", "POST"])
def register():

    # If POST request
    if request.method == "POST":        

        # email id
        email = request.form.get("email")

        # Check if email id is of a developer
        is_dev = check_dev_email(email)

        if not email.endswith('@skit.ac.in') and not is_dev:
            flash("Access Denied. You must log in with a valid SKIT email address.", "danger")
            return redirect(url_for("register"))

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
        
        # Assign role if user is faculty or student
        role = "faculty" if email in faculty_emails else "student"

        # Check if student/faculty is present in users table
        user_present = db.execute("SELECT email, hash_password FROM users WHERE email = ?", email)

        # If user is not present in users (not allowed by admin)
        # And is a student, then don't allow access
        if not user_present and role == "student":
            flash(f"Your Email ID: {email} is not provided access to this portal, please contact Admin.", "warning")
            print(f"Unauthorized user with Email ID: {email} tried to access the portal at {get_current_ist_time()}")
            return redirect("/")

        # If user is present with thier password also,
        # concludes user have manually registered atleast once.
        if user_present and user_present[0]["hash_password"]:
            flash("Email already registered.", "danger")
            return render_template("register.html")

        # If form was filled successfully
        # Convert plain password into a complex string
        hash_password = generate_password_hash(password)

        session['unverified_user'] = {
            'email': email,
            'hash_password': hash_password,
        }
        session['user_role'] = role

        # Verify the user email with an otp
        try:
            send_otp(email)
            flash("A verification code has been sent to your email.", "info")
            return redirect(url_for("otp_verify"))
        except Exception as e:
            print(f"An error occurred while sending OTP: {e}")
            flash("An error occurred while sending the verification email. Please try again.", "danger")
            return redirect(url_for("register"))
    else:
        return render_template("register.html")
    
@app.route("/otp_verify", methods=["GET", "POST"])
def otp_verify():
    # Make sure the user has started the registration process
    # if 'unverified_user' not in session or 'otp_secret' not in session:
    #     flash("Please start the registration process first.", "warning")
    #     return redirect(url_for("register"))

    if request.method == "POST":
        # OTP entered by user
        otp_entered = request.form.get('otp')
        print(f"Actual OTP: {session.get("otp_secret")}, Entered OTP: {otp_entered}")

        # If OTP entered and actual OTP are not same 
        if otp_entered != session.get("otp_secret"):
            print(f"Incorrect OTP entered. Please try again.")
            flash("Wrong OTP entered.Please Check again!","danger")
            return render_template("otpverify.html")

        user_data = session["unverified_user"]

        try:
            # Check if user is a faculty or student
            if session.get("user_role") == 'faculty':
                # Store Faculty's login details in the table
                user_id = db.execute(
                    "INSERT INTO users (email, hash_password, role) VALUES (?, ?, ?)",
                    user_data["email"], user_data["hash_password"], 'faculty'
                    )     
                # Add user_id in faculty_details
                db.execute(
                    "UPDATE faculty_details SET faculty_user_id = ? WHERE college_email = ?", user_id, user_data["email"]
                    ) 
            else:
                # Insert the student data OR update their password if the email already exists
                db.execute("""
                    INSERT INTO users (email, hash_password) 
                    VALUES (?, ?)
                    ON CONFLICT(email) DO UPDATE SET 
                    hash_password = excluded.hash_password
                """, user_data["email"], user_data["hash_password"])
                # Safely grab the ID whether it was just created or just updated
                user = db.execute("SELECT user_id FROM users WHERE email = ?", user_data["email"])
                user_id = user[0]["user_id"]
                
            # Clean session
            session.pop('unverified_user', None)
            session.pop('otp_secret', None)
            session.pop('otp_email', None)
            session['user_id'] = user_id
            flash("Email verified and account created successfully!", "success")

            # Redirect to the appropriate next step
            if session.get('user_role') == 'faculty':
                return redirect(url_for("faculty_dashboard"))
            else:
                flash("Registeration successfull.", "success")
                flash("Please fill student details to access form submission.", "info")
                return redirect(url_for("student_details"))
        except Exception as e:
            flash("A database error occurred. Please try registering again.", "danger")
            print(f"DB Error during user creation: {e}")
            return redirect(url_for("register"))
    
    # Else GET request
    return render_template("otpverify.html")

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
            email = user_info.get('email')

            # Check if email was retrieved
            if not email:
                flash("Could not retrieve email from Google. Please try again.", "danger")
                return redirect(url_for("login"))
            
            # Check if email id is of a developer
            is_dev = check_dev_email(email)

            # Check if the email belongs to the SKIT domain
            if not email.endswith('@skit.ac.in'):
                flash("Email must end with @skit.ac.in", "warning")
                return redirect(url_for("login"))

            google_id = user_info['sub']
            first_name = user_info.get('given_name', '')
            last_name = user_info.get('family_name', '')
            profile_picture = user_info.get('picture', '')

            # Check if user already exists with this Google ID
            existing_user = db.execute("SELECT * FROM users WHERE google_id = ?", google_id)

            if existing_user:
                # User exists, log them into the application session
                session["user_id"] = existing_user[0]["user_id"]
                session["user_role"] = role(session.get("user_id"))
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

                    session["user_role"] = role(session.get("user_id"))

                    flash("Google account linked successfully!", "success")

                # Or new user
                else:
                    # Assign role if user is faculty or student
                    user_role = "faculty" if email in faculty_emails else "student"
                    session["user_role"] = user_role

                    if user_role == "faculty":
                        # New faculty, create a new account in the database with role 'faculty'
                        user_id = db.execute("""
                            INSERT INTO users (email, google_id, auth_provider, profile_picture, first_name, last_name, role)
                            VALUES (?, ?, 'google', ?, ?, ?, ?)
                        """, email, google_id, profile_picture, first_name, last_name, "faculty")
                        session["user_id"] = user_id

                        # Add user_id in faculty_details
                        db.execute("""
                            UPDATE faculty_details SET faculty_user_id = ? WHERE college_email = ?
                        """, user_id, email) 

                        flash("Welcome Faculty! Account created with Google.", "success")
                        return redirect(url_for("faculty_dashboard"))
                    
                    elif user_role == "student":
                        # New student and not present in users table,
                        # Should be first added by admin to get the portal access.
                        flash(f"Your Email ID: {email} is not provided access to this portal, please contact Admin.", "warning")
                        print(f"Unauthorized user with Email ID: {email} tried to access the portal at {get_current_ist_time()}")
                        return redirect(url_for("sodeca_home"))

            if session.get("user_role") == "admin":
                return redirect(url_for("super_admin"))

            if session.get("user_role") == "faculty":
                return redirect(url_for("faculty_dashboard"))
            else:
                filled_student_details = db.execute("SELECT * FROM student_details WHERE student_user_id=?", session["user_id"])
                if not filled_student_details:
                    flash("Please fill student details to access form submission.", "info")
                    return redirect(url_for("student_details"))
                
                return redirect(url_for("sodeca_forms"))
        else:
            flash("Could not fetch user info from Google.", "danger")
            return redirect("/login")
    except Exception as e:
        flash(f"Authentication failed: {e}", "danger")
        return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    # If user already logged in
    if session.get("user_id"):
        return redirect(url_for('sodeca_home'))

    if request.method == "POST":

        email = request.form.get("email")
        if not email:
            flash("Valid SKIT Email is required", "danger")
            return redirect(url_for("login"))
                
        # Check if email id is of a developer
        is_dev = check_dev_email(email)

        if not email.endswith('@skit.ac.in'):
            flash("Access Denied. You must log in with a valid SKIT email address.", "danger")
            return redirect(url_for("login"))

        password = request.form.get("password")
        if not password:
            flash("Password is required", "danger")
            return redirect("/login")

        rows = db.execute(
            "SELECT user_id, email, hash_password, auth_provider FROM users WHERE email = ?", email
            )

        # If user never registered
        if len(rows) != 1 :
            flash("Email does not exist, please go to register.", "danger")
            return redirect("/login")
        
        # User only used sign-in with Google,
        # Means user never registered a password
        elif not rows[0]["hash_password"] :
            flash("Please register your Email with a password.", "danger")
            return redirect("/register")
        
        elif not check_password_hash(
            rows[0]["hash_password"], password
            ):
            flash("Invalid password or email", "danger")
            return redirect("/login")

        # Remember the user if login was successful
        user_id = rows[0]["user_id"]
        session["user_id"] = user_id

        user_role = role(session.get("user_id"))
        session["user_role"] = user_role

        update_faculty_emails()

        # If Admin
        if user_role == 'admin':
            return redirect(url_for("super_admin"))

        # If Coordinator
        elif user_role == 'coordinator':
            return redirect(url_for("coordinator"))

        # If Faculty
        elif email in faculty_emails:
            user_role = 'faculty' 
            return redirect(url_for("faculty_dashboard"))
        
        # If Student
        elif user_role == 'student':
            details_filled = db.execute("SELECT student_user_id FROM student_details WHERE student_user_id = ?", user_id)
            # If student has not filled details
            if not details_filled:
                # Fill details first
                flash("Login successful.", "success")
                flash("Please fill student details to access form submission.", "info")
                return redirect(url_for("student_details"))
            
            flash("Login successful.", "success")
            return redirect(url_for("sodeca_home"))
                
        flash("Invalid username/password", "danger")
        return url_for("login")
    else:
        return render_template("login.html")

@app.route('/authorize_drive')
@login_required
def authorize_drive():
    """Handles Drive AUTHORIZATION for faculty. Asks only for Drive permission."""
    
    # We store this in the session to "remember" it across the Google redirect
    session['drive_auth_redirect_target'] = request.referrer or url_for('faculty_dashboard')

    redirect_uri = url_for('drive_callback', _external=True)
    
    return google_drive_client.authorize_redirect(
        redirect_uri, 
        access_type="offline", 
        prompt="consent"
    )

@app.route('/auth/google/drive_callback')
@login_required
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
    
    # 3. Retrieve the stashed URL (and remove it from session so it doesn't linger)
    # If the key is missing for some reason, fallback to 'faculty_dashboard'
    next_url = session.pop('drive_auth_redirect_target', url_for('faculty_dashboard'))

    return redirect(next_url)

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

        # Get name of student
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

        # Get Section Group
        selected_section = request.form.get("section_option")
        if not selected_section:
            return redirect("/student_details")

        # Get Batch Counselor name
        batch_counselor = db.execute("""SELECT full_name FROM faculty_details WHERE semester=? AND
                    branch=? AND section=?""",
                    selected_semester, selected_branch,
                    selected_section)
        if batch_counselor:
            batch_counselor_name = batch_counselor[0]["full_name"]
        else:
            batch_counselor_name = None

        try:
            # If all entries are filled successfuly
            # Store detail using UPSERT query
            # The corrected and robust "UPSERT" command
            db.execute(
                """
                INSERT INTO student_details (
                    student_user_id, university_roll_no, student_name, branch,
                    semester, section, batch_counselor
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(student_user_id) DO UPDATE SET
                    university_roll_no = excluded.university_roll_no,
                    student_name = excluded.student_name,
                    branch = excluded.branch,
                    semester = excluded.semester,
                    section = excluded.section,
                    batch_counselor = excluded.batch_counselor
                """,
                session["user_id"], university_roll_no, student_name, selected_branch,
                selected_semester, selected_section, batch_counselor_name
            )
        except Exception as e:
            flash(f"Database error: {e}")
            return redirect(url_for("student_details"))
        
        flash("Your details were successfully saved.", "success")

        # Get the next URL from form or query parameter
        next_url = request.args.get('next')
        
        print(next_url)
        # Validate the URL for security
        if next_url and is_safe_url(next_url):
            return redirect(next_url)
    
        return redirect(url_for("sodeca_forms"))
    
    else:
        curr_settings = db.execute("SELECT academic_session, academic_term FROM drive_settings")
        if not curr_settings:
            flash("System not configured yet.", "warning")
            return redirect(url_for("sodeca_home.html"))
        
        curr_academic_session = curr_settings[0]["academic_session"]
        curr_academic_term = curr_settings[0]["academic_term"]

        # Already available student details
        # Variable stores a list of dictionaries
        # Student information
        student_details_row = db.execute(
            "SELECT * FROM student_details WHERE student_user_id = ?", session["user_id"]
        )

        branch_list = [None]
        semester = [None]
        section_set = [None]

        # Branch and Semester data
        semester = db.execute("""
            SELECT DISTINCT sem FROM batch_structure 
            WHERE academic_session=? AND academic_term=? ORDER BY sem ASC
        """, curr_academic_session, curr_academic_term)

        branch_list = db.execute("""
            SELECT DISTINCT branch FROM batch_structure 
            WHERE academic_session=? AND academic_term=? ORDER BY branch ASC
        """, curr_academic_session, curr_academic_term)         

        # If details are already available
        if student_details_row:
            filled_details = student_details_row[0]

            # Get faculty name assigned to the student's batch
            batch_counselor = db.execute("""SELECT full_name FROM faculty_details WHERE semester=? AND
                                branch=? AND section=?""",
                                filled_details["semester"], filled_details["branch"],
                                filled_details["section"])
            if batch_counselor:
                batch_counselor_name = batch_counselor[0]["full_name"]
            else:
                batch_counselor_name = None
            
            # Show the page with filled details
            return render_template(
                "student_details.html", details=filled_details, 
                branches=branch_list, semester=semester, 
                batch_counselor_name=batch_counselor_name
                )
        else:
            return render_template(
                "student_details.html", branches=branch_list, 
                semester=semester, details=None, 
                faculty_name=None
                )

@app.route('/api/sections', methods=['GET'])
def get_sections():
    # 1. Extract query parameters
    sem_raw = request.args.get('sem')
    branch = request.args.get('branch')

    # 2. Presence Check
    if not sem_raw or not branch:
        return jsonify({"error": "Missing parameters. Both 'sem' and 'branch' are required."}), 400

    # 3. Explicit Type Sanitization
    try:
        sem = int(sem_raw)  # Safely forces the semester to be an integer
    except ValueError:
        return jsonify({"error": "Invalid parameter type. 'sem' must be a valid integer."}), 400

    # Strip any accidental leading/trailing whitespace from text inputs
    branch = branch.strip()

    curr_settings = db.execute("SELECT academic_session, academic_term FROM drive_settings")
    if not curr_settings:
        return jsonify({"error": "No batch settings configured yet."}), 400

    curr_academic_session = curr_settings[0]["academic_session"]
    curr_academic_term = curr_settings[0]["academic_term"]

    try:        
        # 4. Parameterized Query execution remains secure
        query = """
            SELECT section 
            FROM batch_structure 
            WHERE sem=? AND branch=?
            AND academic_session=? AND academic_term=?
            ORDER BY section ASC;
        """
        rows = db.execute(query, sem, branch, curr_academic_session, curr_academic_term)
        sections_list = [row['section'] for row in rows]
        return jsonify(sections_list), 200
        
    except Exception as e:
        # Avoid exposing detailed system errors in production environments
        return jsonify({"error": "An internal database error occurred."}), 500

@app.route("/sodeca_forms", methods=["GET", "POST"])
def sodeca_forms():

    if request.method == "POST":
        selected_forms = request.form.getlist('selected_forms[]') # e.g., ['form1', 'form3', 'form5']

        # Store the list and the starting point (index 0) in the session
        session['selected_forms'] = selected_forms
        session['current_form_index'] = 0
        
        session.pop("verified_details", None)

        # redirect to fill form
        return redirect("/verify_student_details")
    else:
        return render_template("sodeca_forms.html", FORM_DEFINITIONS=FORM_DEFINITIONS)

@app.route("/verify_student_details", methods=["GET", "POST"])
@login_required
def verify_student_details():

    # If student checked and clicked next
    if request.method == "POST":

        verified_details = request.form.get("verified_details")
        session["verified_details"] = verified_details

        academic_session_row = db.execute("SELECT academic_session, academic_term FROM drive_settings")
        if not academic_session_row:
            print("System for this acadmeic session and term not configured, please contact admin")
            flash("System for this acadmeic session and term not configured, please contact admin", "danger")
            return redirect(url_for('sodeca_forms'))
        
        session["academic_session"] = academic_session_row[0].get("academic_session")
        session["academic_term"] = academic_session_row[0].get("academic_term")

        print(f"Verified: {verified_details}")
        return redirect(url_for('fill_form'))
    else:
        # Get student details if already present
        # Variable stores a list of dictionaries
        student_details_row = db.execute(
                    "SELECT * FROM student_details WHERE student_user_id = ?", session["user_id"]
                    )
        
        # If details are already available
        if not student_details_row:
            flash("Please submit student details before proceeding.", "warning")
            return redirect(url_for('student_details'))

        session["student_details"] = student_details_row[0]

        # Show the page with filled details
        return render_template("verify_student_details.html", details=student_details_row[0])

@app.route("/fill_form", methods=["GET", "POST"])
@login_required
def fill_form():
    # Safety fix    
    # If user has not verified details
    if session.get("verified_details") == None:
        flash("Kindly confirm details by checking the checkbox", "warning")
        return redirect("/verify_student_details")
        
    # If not selected any forms, first go and select
    if not session.get("selected_forms"):
        flash("Please select atleast one form to submit", "danger")
        return redirect(url_for("sodeca_forms"))

    user_id = session["user_id"]
    selected_forms = session["selected_forms"]
    current_form_index = session["current_form_index"]
    total_count = len(selected_forms)

    print(f"{current_form_index} and {total_count}")

    # If all forms are completed
    if current_form_index >= len(selected_forms):

        print("I am about to pop out session hahaha!")
        # Clean up the session
        session.pop("selected_forms", None)
        session.pop("current_form_index", None)
        session.pop("academic_session")
        session.pop("academic_term")
        session.pop("student_details")

        session["finished_all_forms"] = True

        flash("Submission successfull! Kindly check your submissions on your submissions page", "success")
        return redirect(url_for("sodeca_home"))

    # current_form_index is the key in dict "selected_forms" defined in the start
    current_form = selected_forms[current_form_index]
    form_to_show = FORM_DEFINITIONS[current_form]

    if request.method == "POST":

        # Initialise dict for text and radio inputs
        form_inputs = {}
        from_date = None
        to_date = None

        # Initialise in this scope the google_file_id
        save_path = ""

        # Check if certificate was submitted
        if current_form != 'placement_offer' and 'certificate' not in request.files:
            flash("No file part", "danger")
            return redirect(request.url)

        # Iterating through all input fields
        for field in form_to_show["fields"]:

            field_title = field["field_label"]
            field_name = field["field_name"]
            field_type = field["field_type"]
            field_required = field["required"]

            # If input field is a date
            if field_type == "date":
                if request.form.get(field_name):
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
                    
                    # If its placement offers then do not rename pdf
                    if current_form != 'placement_offer':
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

                        certificate.filename = f"{uni_roll_no}_{student_name}_{event_name}{file_extension}"

                    # Secure the filename to prevent security risks (e.g., directory traversal)
                    filename = secure_filename(certificate.filename)
                    
                    # Handle duplicate filenames by adding a number in parentheses
                    base_name, extension = os.path.splitext(filename)
                    save_path = os.path.join(UPLOAD_FOLDER, filename)
                    counter = 1
                    
                    while os.path.exists(save_path):
                        filename = f"{base_name}({counter}){extension}"
                        save_path = os.path.join(UPLOAD_FOLDER, filename)
                        counter += 1
                    
                    # Save filename in form_inputs
                    form_inputs[field_name] = filename

                    # Save the file to the local server
                    certificate.save(save_path)
                else:
                    flash("Invalid file type. Allowed types are: pdf", "danger")
                    return redirect(request.url)
            # Text and Radio inputs
            else:
                # Update form_inputs dict
                if request.form.get(field_name):
                    form_inputs[field_name] = request.form.get(field_name)
                # TODO: Error Handling

            # If any required input is missing
            if field_required and not form_inputs[field_name]:
                # flash error
                flash(f"Submission Failed: {field_title} is required!", "danger")
                return redirect(request.url)

            # Debugging
            try:
                print(f"{field_title}: {form_inputs[field_name]}")
            except KeyError:
                print(f"{field_title}: Not a Required Key")

        # Error checking using "date_object"
        if from_date and to_date:
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
                    INSERT INTO {current_form} (student_id, sem, branch, section, academic_session, academic_term, {form_fields_sql}, full_path, google_file_id, status, submitted_at)
                    VALUES(?, ?, ?, ?, ?, ?, {placeholder_sql}, ?, ?, ?, datetime('now', '+5 hours', '+30 minutes'))
                """, session["user_id"], session.get("student_details")["semester"], session.get("student_details")["branch"], session.get("student_details")["section"],
                session.get("academic_session"), session.get("academic_term"), *values_list, # *values_list gives a string eg. "Value1", "Value2"...
                save_path, "pending", "pending")

            except Exception as e:
                print(f"Database error: {e}", file=sys.stderr)
                flash("A database error occurred while saving the form. Please try again later.", "danger")

                # IMPORTANT: If the DB save fails, we should delete the file we just saved

                return redirect(request.url)

        # Update form number
        session["current_form_index"] += 1

        # Form submission successful, show success page
        percentage = ((current_form_index+1) / total_count) * 100
        return render_template("fill_form.html", success=True, form_to_show=form_to_show, count=current_form_index, progress_width=percentage, total=total_count)

    # Just show the form to be filled
    percentage = (current_form_index / total_count) * 100
    return render_template("fill_form.html", success=False, form_to_show=form_to_show, count=current_form_index, progress_width = percentage, total=total_count)

# View user submissions route
@app.route("/your_submissions", methods=["GET"])
@login_required
def your_submissions():
    student_id = session.get("user_id")
    base_queries = []
    params = {'sid': student_id}

    for key, value in FORM_DEFINITIONS.items():
        base_queries.append(
                f"""SELECT entry_id, '{key}' AS form_name, '{value["title"]}' AS form_title, 
                certificate, status, submitted_at, withdrawn_at, rejection_note
                FROM {key} WHERE student_id = :sid"""
                )
    if base_queries:
        complete_query = " UNION ALL ".join(base_queries)
        final_sql = f"{complete_query} ORDER BY submitted_at DESC"

        try:
            # Execute the combined query with the named parameter
            submissions = db.execute(final_sql, **params)
        except Exception as e:
            print(f"Error fetching submissions for student {student_id}: {e}")
            flash("An error occurred while fetching your submissions.", "danger")
            return redirect(url_for('sodeca_forms'))

        # For loops on sessions

    return render_template("your_submissions.html", submissions=submissions)

@app.route("/view_details", methods=["POST"])
@login_required
def view_details():
    """
    Handles a background request to fetch details for a single submission.
    Expects JSON: { "entry_id": 123, "form_name": "blood_donor" }
    Returns JSON: { "details": {...} }
    """
    try:
        data = request.get_json()
        entry_id = data.get('entry_id')
        form_name = data.get('form_name')

        # --- CRITICAL SECURITY CHECK ---
        if form_name not in FORM_DEFINITIONS:
            print(f"Error: Invalid form name requested: {form_name}", file=sys.stderr)
            return jsonify({"error": "Invalid form type."}), 400

        if not entry_id:
            return jsonify({"error": "Entry id not available"}), 400

        # Securely query the database
        entry_details = db.execute(
            f"SELECT * FROM {form_name} WHERE entry_id = :sid",
            sid=entry_id
        )

        if not entry_details:
            return jsonify({"error": "Entry not found."}), 404
            
        details_dict = entry_details[0]
        
        return jsonify({"details": details_dict})

    except Exception as e:
        print(f"Error in /view_details: {e}", file=sys.stderr)
        return jsonify({"error": "A server error occurred. Please try again."}), 500

@app.route("/withdraw_entry", methods=["POST"])
@login_required
def withdraw_entry():
    entry_id = request.form.get("entry_id")
    form = request.form.get("form_name")
    print(f"Withdrawing entry from table: {form}")

    try:
        db.execute(f"UPDATE {form} SET withdrawn_at = datetime('now', '+5 hours', '+30 minutes') WHERE entry_id = ?", entry_id)
        flash("Entry withdrawn", "success")

    except Exception as e:
        print(f"Database error: {e}")
        flash(f"An unexpected error occured, please contact Admin", "danger")
    return redirect(url_for("your_submissions"))

def student_submission_stats(batch_details):
    """
    Fetches ALL students for the batch with 'Smart Sorting' applied.
    Data is passed to the frontend for client-side JavaScript pagination
    and Python-side Grand Total calculation.
    """
    
    # 1. Build the Activity Stream
    subqueries = []
    for form in form_name_list:
        subqueries.append(f"""
            SELECT student_id, status, submitted_at 
            FROM {form} 
            WHERE withdrawn_at IS NULL
        """)
    
    master_union = " UNION ALL ".join(subqueries)

    # 2. Build the Master Query WITHOUT Limits
    final_sql = f"""
        WITH FormActivities AS (
            {master_union}
        ),
        StudentFormCounts AS (
            SELECT 
                student_id,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
                SUM(CASE WHEN status = 'accepted' THEN 1 ELSE 0 END) AS accepted_count,
                SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
                MAX(CASE WHEN status = 'pending' THEN submitted_at ELSE NULL END) as latest_pending_date
            FROM FormActivities
            GROUP BY student_id
        )
        SELECT 
            s.student_user_id,
            s.student_name,
            s.university_roll_no,
            COALESCE(c.pending_count, 0) AS pending_count,
            COALESCE(c.accepted_count, 0) AS accepted_count,
            COALESCE(c.rejected_count, 0) AS rejected_count
        FROM student_details s
        LEFT JOIN StudentFormCounts c ON s.student_user_id = c.student_id
        WHERE s.semester = ? 
          AND s.branch = ? 
          AND s.section = ? 
        ORDER BY 
            CASE WHEN COALESCE(c.pending_count, 0) > 0 THEN 0 ELSE 1 END ASC,
            c.latest_pending_date DESC,
            s.university_roll_no ASC
    """

    # Base parameters for the batch
    base_params = [
        batch_details["semester"], 
        batch_details["branch"], 
        batch_details["section"], 
    ]

    try:
        # Execute the main query and return the full list of students
        students = db.execute(final_sql, *base_params)
        return students
        
    except Exception as e:
        print(f"Error fetching student stats: {e}", file=sys.stderr)
        return []
    
# Page for the faculty, to check submissions
# Faculty can do get and post request
@app.route("/faculty_dashboard", methods=["GET"])
@login_required
def faculty_dashboard():
    if request.method == "GET":

        if role(session.get("user_id")) != 'faculty' and role(session.get("user_id")) != 'tester':
            return "Access Denied!", 400
        
        # Initialize count of all student's pending, accepted and rejected 
        # submissions requests from your batch
        submission_counts = {
            "pending": 0,
            "accepted": 0,
            "rejected": 0
        }
        
        # Get batch details, assigned to faculty
        batch = db.execute("SELECT semester, branch, section FROM faculty_details WHERE faculty_user_id = ?", session["user_id"])
        
        # If batch is not assigned by admin
        if not batch:
            return render_template("faculty_dashboard.html",
                                batch_is="No Batch Assgined...",
                                submission_counts=submission_counts,
                                students=None,
                                )
        batch_details = batch[0]
        # Extract and sanitize details (defaulting to empty strings/None)
        sem = batch_details.get('semester')
        branch = batch_details.get('branch')
        section = batch_details.get('section')

        # Build components dynamically if they exist
        parts = []

        if sem or branch:
            # Combine semester and branch directly (e.g., "3CS")
            sem_branch = f"{sem or ''}{branch or ''}"
            if sem_branch:
                parts.append(sem_branch)

        if section:
            parts.append(str(section))

        # Join the parts with a hyphen, or set to None if all are empty
        batch_is = "-".join(parts) if parts else None
        if (batch_is != None):
            session["batch_details"] = batch_details
    
        # Submission requests stats of individual student in the batch
        students = student_submission_stats(batch_details)
        print(students)
        for student in students:
            submission_counts["pending"] += student["pending_count"]
            submission_counts["accepted"] += student["accepted_count"]
            submission_counts["rejected"] += student["rejected_count"]

        return render_template("faculty_dashboard.html",
                                batch_is=batch_is,
                                submission_counts=submission_counts,
                                students=students,
                                )

@app.route("/batch_report", methods=["GET","POST"])
def batch_report():
    if not session.get("batch_details"):
        flash("Batch is not assigned. Contact Admin", "danger")
        return redirect("faculty_dashboard")
    
    batch_details = session.get("batch_details")
    
    if request.method == "POST":
        data = request.get_json()
        form_id = data.get('form_id')

        result = db.execute(f"""SELECT * FROM {form_id} as f
                            INNER JOIN student_details as s 
                            ON f.student_id = s.student_user_id
                            WHERE s.branch=? AND s.semester=? AND s.section=?""",
                            batch_details["branch"], batch_details["semester"],
                            batch_details["section"])

        col_labels = ['Entry ID', 'Univ. Roll Num.', 'Student Name', 'Batch Counselor']
        sql_cols = ['entry_id', 'university_roll_no', 'student_name', 'batch_counselor']

        for field in FORM_DEFINITIONS[form_id]["fields"]:
            col_labels.append(field["field_label"])
            sql_cols.append(field["field_name"])

        col_labels.extend(['Google_file_id','Status','Submitted At'])
        sql_cols.extend(['google_file_id','status','submitted_at'])

        # If selected form has no entries
        if not result:
            return jsonify({'success': False, 'message': 'No data available'})

        return jsonify({'success': True, 'row_values': result, 'sql_col':sql_cols, 'column_name': col_labels})

    if request.method == "GET":
        result = db.execute(f"""SELECT * FROM blood_donor as f
                            INNER JOIN student_details as s 
                            ON f.student_id = s.student_user_id
                            WHERE f.withdrawn_at IS NULL 
                            AND s.branch=? AND s.semester=? AND s.section=?""",
                            batch_details["branch"], batch_details["semester"],
                            batch_details["section"])
                
        return render_template("batch_report.html", form_dict=form_dict, rows=result)

@app.route("/review_student", methods=["GET"])
@login_required
def review_student():
    student_user_id = request.args.get("id")

    if not student_user_id:
        flash("Invalid Student ID", "danger")
        return redirect(url_for("faculty_dashboard"))

    student_profile_data = db.execute(
        "SELECT * FROM student_details WHERE student_user_id = ?", 
        student_user_id
    )

    if not student_profile_data:
        flash("Student not found in database.", "danger")
        return redirect(url_for("faculty_dashboard"))
        
    student_profile = student_profile_data[0]
    faculty_assigned_batch = session["batch_details"]

    student_branch = student_profile['branch']
    if (faculty_assigned_batch['branch'] != student_branch):
        flash("Student's batch is out of your assigned scope. To access data of other batch students, contact Admin.", "danger")
        return redirect(url_for("faculty_dashboard"))

    student_sem = student_profile['semester']
    if (faculty_assigned_batch['semester'] != student_sem):
        flash("Student's batch is out of your assigned scope. To access data of other batch students, contact Admin.", "danger")
        return redirect(url_for("faculty_dashboard"))

    student_section = student_profile['section']
    if (faculty_assigned_batch['section'] != student_section):
        flash("Student's batch is out of your assigned scope. To access data of other batch students, contact Admin.", "danger")
        return redirect(url_for("faculty_dashboard"))

    batch_str = f"{student_sem}_{student_branch}_{student_section}"

    # Fetch all form submissions without any JOINs
    submissions = []
    
    for form in form_name_list:
        try:
            # Simple, direct index lookup. Blazingly fast.
            # We fetch f.* as requested to get all specific details.
            form_data = db.execute(f"""
                SELECT *,
                '{form}' as form_name 
                FROM {form}
                WHERE student_id = ? 
                AND withdrawn_at IS NULL
                ORDER BY submitted_at DESC
            """, student_user_id)
            
            # Only add to our dictionary if they actually have submissions for this form
            if form_data:
                submissions.extend(form_data)

        except Exception as e:
            print(f"Error fetching data from {form} for student {student_user_id}: {e}", file=sys.stderr)

    # Creating data for summary table
    summary_dict = {}
    total_dict = {'pending': 0, 'accepted': 0, 'rejected': 0}

    for submission in submissions:

        form_name = submission["form_name"]
        status = submission['status']

        if not summary_dict.get(form_name):
            summary_dict[form_name] = {'pending': 0, 'accepted': 0, 'rejected': 0}
        
        summary_dict[form_name][status] += 1
        total_dict[status] += 1

    return render_template("review_student.html", 
                            form_dict=form_dict,                   
                            summary_dict=summary_dict, 
                            submissions=submissions, 
                            total_dict=total_dict,
                            student_profile=student_profile,
                            batch_str=batch_str
                            )

@app.route('/view_submission/<path:filename>') 
@login_required
def view_submission(filename):

    """Securely serves a file from the local upload folder for faculty to view."""
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

def upload_single_file(entry_id, form_name, filename, batch_str, token, job_id, client_id, client_secret):
    """Worker function that runs in a background thread for each file upload."""
    full_path = os.path.join(UPLOAD_FOLDER, filename)

    # Mark this file as uploading in the shared tracker
    with job_status_lock:
        job_status[job_id]["files"][entry_id]["status"] = "uploading"

    try:
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Local file not found: {full_path}")

        to_search_id = f"{batch_str}_{form_name}"
        drive_folder = db.execute(
            "SELECT drive_folder_id FROM drive_folder_map WHERE id=?", 
            to_search_id
        )

        if not drive_folder:
            raise ValueError(f"Drive folder not found for: {to_search_id}")

        drive_folder_id = drive_folder[0]["drive_folder_id"]

        access_token = token.get('access_token') or token.get('token')
        refresh_token = token.get('refresh_token')

        credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret
        )

        import socket
        socket.setdefaulttimeout(300)

        drive_service = build('drive', 'v3', credentials=credentials)
        file_metadata = {'name': filename, 'parents': [drive_folder_id]}
        media = MediaFileUpload(full_path, resumable=False)

        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name'
        ).execute()

        google_file_id = uploaded_file.get('id')

        # Only update DB after Drive confirms success — prevents inconsistent state
        sql_query = f"UPDATE {form_name} SET status = :status, google_file_id = :gfid WHERE entry_id = :sid"
        db.execute(sql_query, status="accepted", gfid=google_file_id, sid=entry_id)

        # Mark success in shared tracker
        with job_status_lock:
            job_status[job_id]["files"][entry_id]["status"] = "done"
            job_status[job_id]["files"][entry_id]["filename"] = uploaded_file.get('name')
            job_status[job_id]["completed"] += 1

    except Exception as e:
        print(f"Upload failed for entry {entry_id}: {e}", file=sys.stderr)
        # Mark failure — DB is NOT updated, stays as pending
        with job_status_lock:
            job_status[job_id]["files"][entry_id]["status"] = "failed"
            job_status[job_id]["files"][entry_id]["error"] = str(e)
            job_status[job_id]["failed"] += 1

@app.route("/upload_to_drive", methods=["POST"])
@login_required
@drive_auth_required
def upload_to_drive():
    """Uploads a file using the authorized Drive client."""
    token = session.get('drive_auth_token')
    if not token:
        flash("Drive authorization required. Please authorize your account first.", "warning")
        return redirect(request.referrer)

    filename = request.form.get('filename')
    entry_id = request.form.get('entry_id')
    form_name = request.form.get('form_name')
    print(filename)
    print(UPLOAD_FOLDER)
    full_path = os.path.join(UPLOAD_FOLDER, filename)

    if not os.path.exists(full_path):
        flash(f"Error: Local file not found at {full_path}", "danger")
        return redirect(request.referrer)

    batch_str = request.form.get("batch_str")
    print(batch_str)

    to_search_id = f"{batch_str}_{form_name}"
    drive_folder = db.execute("SELECT drive_folder_id FROM drive_folder_map WHERE id=?", to_search_id)
    
    if drive_folder:
        drive_folder_id = drive_folder[0]["drive_folder_id"]
        print(drive_folder_id)
    else:
        # Handle the error gracefully
        print(f"Critical Error: Drive folder not found for ID: {to_search_id}")
        flash("Destination folder not found in Drive map. Please contact Admin.", "danger")
        return redirect(request.referrer)

    # Get participation and achievement folder ids
    submission_category = request.form.get('submission_category')
    if not submission_category:
        flash("Error: Submission category is null", "danger")
        return redirect(request.referrer)

    submission_folder_id = None

    if (submission_category == "achievement"):
        achievement_folder_list = db.execute("SELECT achievement_folder_id FROM drive_settings")
        if (achievement_folder_list):
            submission_folder_id = achievement_folder_list[0].get("achievement_folder_id")

    elif (submission_category == "participation"):
        participation_folder_list = db.execute("SELECT participation_folder_id FROM drive_settings")
        if (participation_folder_list):
            submission_folder_id = participation_folder_list[0].get("participation_folder_id")

    if (not submission_folder_id):
        flash("Error: Submission category is NULL", "danger")
        return redirect(request.referrer)
    
    try:
        # 1. Safely extract the tokens from your session dictionary
        access_token = token.get('access_token') or token.get('token')
        refresh_token = token.get('refresh_token')

        # 2. Safely grab the Client ID and Secret directly from Flask config
        # (This prevents scope issues where global variables become None)
        
        client_id = current_app.config.get("GOOGLE_CLIENT_ID")
        client_secret = current_app.config.get("GOOGLE_CLIENT_SECRET")
        
        # 3. Build the Credentials object
        credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id, 
            client_secret=client_secret
        )

        import socket
        socket.setdefaulttimeout(300)

        drive_service = build('drive', 'v3', credentials=credentials)

        file_metadata = {'name': filename, 'parents': [drive_folder_id]}
        file_metadata_submission_category = {'name': filename, 'parents': [submission_folder_id]}
        
        media_batch = MediaFileUpload(full_path, resumable=False)

        # upload file to respective batch folder
        uploaded_file = drive_service.files().create(
            body=file_metadata, media_body=media_batch, fields='id,name'
        ).execute()

        google_file_id = uploaded_file.get('id')

        # Upload file to either achievement or participation folder
        media_submission_category = MediaFileUpload(full_path, resumable=False)
        try:
            submission_category_file = drive_service.files().create(
                body=file_metadata_submission_category, media_body=media_submission_category, fields='id,name'
            ).execute()

            if not submission_category_file.get('id'):
                raise Exception("Category folder upload returned no file ID")

        except Exception as category_upload_error:
            # First upload succeeded but second failed - clean up to avoid an orphaned file
            try:
                drive_service.files().delete(fileId=google_file_id).execute()
            except Exception as cleanup_error:
                print(
                    f"Failed to clean up orphaned file {google_file_id} after category upload failure: {cleanup_error}"
                )
            raise

        sql_query = f"UPDATE {form_name} SET status = :status, google_file_id = :gfid WHERE entry_id = :sid"
        db.execute(sql_query, status="accepted", gfid=google_file_id, sid=entry_id)

        # 3. CRITICAL: If the token was refreshed during the upload, save the new one back to the session!
        if credentials.token != access_token:
            token['access_token'] = credentials.token
            session['drive_auth_token'] = token
            session.modified = True

        flash(f"Successfully uploaded file '{uploaded_file.get('name')}'", "success")

    except HttpError as error:
        # This error happens if the token is expired, invalid, or revoked.
        if error.resp.status in [400, 401]:
            # The token is bad. Remove it from the session.
            session.pop('drive_auth_token', None)
            # Send the user a helpful message and prompt them to log in again.
            flash("Your Google authorization has expired or was revoked. Please authorize again.", "warning")
            # Redirecting to the dashboard will now show the "Login with Google" button.
            return redirect(request.referrer)
        else:
            # For other API errors (e.g., 500 server error), just show the error.
            flash(f"An API error occurred: {error}", "danger")

    except Exception as e:
        print(f"An unexpected error occurred in upload_to_drive: {e}", file=sys.stderr)
        flash(f"An unexpected error occurred: {e}", "danger")

    return redirect(request.referrer)

@app.route("/bulk_upload_to_drive", methods=["POST"])
@login_required
@drive_auth_required
def bulk_upload_to_drive():
    """Accepts multiple submissions concurrently using a thread pool."""
    token = session.get('drive_auth_token')
    if not token:
        return {"error": "Drive authorization required"}, 401

    # Parse list of submissions from frontend
    submissions = request.json.get('submissions', [])
    if not submissions:
        return {"error": "No submissions provided"}, 400

    client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    client_secret = current_app.config.get("GOOGLE_CLIENT_SECRET")

    # Create a unique job ID for this bulk upload session
    job_id = str(uuid.uuid4())

    # Initialize job tracker with all files as pending
    with job_status_lock:
        job_status[job_id] = {
            "total": len(submissions),
            "completed": 0,
            "failed": 0,
            "files": {
                str(s['entry_id']): {
                    "status": "pending",
                    "filename": s['filename']
                }
                for s in submissions
            }
        }

    # Launch thread pool — max 3 concurrent uploads to respect Drive API limits
    def run_pool():
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(
                    upload_single_file,
                    str(s['entry_id']),
                    s['form_name'],
                    s['filename'],
                    s['batch_str'],
                    token,
                    job_id,
                    client_id,
                    client_secret
                ): s for s in submissions
            }

    # Run pool in a background thread so route returns immediately
    pool_thread = threading.Thread(target=run_pool)
    pool_thread.daemon = True
    pool_thread.start()

    return {"job_id": job_id}, 202

@app.route("/upload-status/<job_id>", methods=["GET"])
@login_required
def upload_status(job_id):
    """Faculty frontend polls this to get live upload progress."""
    with job_status_lock:
        job = job_status.get(job_id)
        if not job:
            return {"error": "Job not found"}, 404
        # Return a copy to avoid holding the lock during JSON serialization
        return dict(job)

@app.route("/reject_entry", methods=["POST"])
@login_required
def reject_entry():
    entry_id = request.form.get("entry_id")
    form_name = request.form.get("form_name")
    rejection_note = request.form.get("rejection_note", None)
    if rejection_note == '':
        rejection_note = None
        
    try:
        # Update status of entry and add the rejection_note
        sql_query = f"UPDATE {form_name} SET status='rejected', rejection_note=? WHERE entry_id=?"
        db.execute(sql_query, rejection_note, entry_id)

    except Exception as e:
        flash(f"Database error: {e}")
        return redirect(request.referrer)
    
    return redirect(request.referrer)

def get_sem_options(academic_session=None, academic_term=None):
    query = "SELECT DISTINCT sem FROM batch_structure"
    conditions = []
    
    if academic_session:
        sessions = ", ".join(f"'{s}'" for s in academic_session)
        conditions.append(f"academic_session IN ({sessions})")

    if academic_term:
        terms = ", ".join(f"'{t}'" for t in academic_term)
        conditions.append(f"academic_term IN ({terms})")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY sem"

    print(query)
    return db.execute(query)

def get_branch_options(academic_session=None, academic_term=None, semester=None):
    query = "SELECT DISTINCT branch FROM batch_structure"
    conditions = []
    
    if academic_session:
        sessions = ", ".join(f"'{s}'" for s in academic_session)
        conditions.append(f"academic_session IN ({sessions})")

    if academic_term:
        terms = ", ".join(f"'{t}'" for t in academic_term)
        conditions.append(f"academic_term IN ({terms})")

    if semester:
        semesters = ", ".join(f"'{sem}'" for sem in semester)
        conditions.append(f"sem IN ({semesters})")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY sem"

    print(query)
    return db.execute(query)

def get_section_options(academic_session=None, academic_term=None, semester=None):
    query = "SELECT DISTINCT section FROM batch_structure"
    conditions = []
    
    if academic_session:
        sessions = ", ".join(f"'{s}'" for s in academic_session)
        conditions.append(f"academic_session IN ({sessions})")

    if academic_term:
        terms = ", ".join(f"'{t}'" for t in academic_term)
        conditions.append(f"academic_term IN ({terms})")

    if semester:
        semesters = ", ".join(f"'{sem}'" for sem in semester)
        conditions.append(f"sem IN ({semesters})")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY branch"

    print(query)
    return db.execute(query)

@app.route("/coordinator", methods=["GET"])
@login_required
def coordinator():
    if session.get("user_role") != "coordinator":
        abort(404)

    return render_template("coordinator.html")

@app.route("/super_admin", methods=["GET"])
@login_required
def super_admin():
    if session.get("user_role") != "admin":
        abort(404)

    return render_template("super_admin.html")

@app.route("/faculty_management", methods=["GET", "POST"])
@login_required
def faculty_management():
    user_role = session.get("user_role")
    if user_role != "admin" and user_role != "coordinator":
        abort(404)

    # Add/Update new faculty
    if request.method == "POST":
        full_name = request.form.get("full_name")
        if not full_name:
            flash("Name is a required field", "danger")
            return redirect(url_for("faculty_management"))
        college_email = request.form.get("college_email")
        if not college_email:
            flash("Email is a required field", "danger")
            return redirect(url_for("faculty_management"))
        designation = request.form.get("designation")
        if not designation:
            flash("Designation is a required field", "danger")
            return redirect(url_for("faculty_management"))
        department = request.form.get("department")
        if not department:
            flash("Department is a required field", "danger")
            return redirect(url_for("faculty_management"))
        contact = request.form.get("contact")
        if not contact:
            contact = 'to be updated'

        # Check if user exists with this email
        existing_user = db.execute(
            "SELECT user_id FROM users WHERE email = ?", 
            college_email
        )
        user_id = existing_user[0]["user_id"] if existing_user else None

        try:
             
            # UPSERT faculty_details with user_id
            db.execute(
                """
                INSERT INTO faculty_details (
                    college_email, faculty_user_id, full_name, designation, department, contact
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(college_email) DO UPDATE SET
                    faculty_user_id = excluded.faculty_user_id,
                    full_name = excluded.full_name,
                    designation = excluded.designation,
                    department = excluded.department,
                    contact = excluded.contact
                """,
                college_email, user_id, full_name, designation, department, contact
            )
            
            # Update faculty_emails list if needed
            if college_email not in faculty_emails:
                update_faculty_emails()

            if existing_user:
                # Ensure they're marked as faculty
                db.execute(
                    "UPDATE users SET role = 'faculty' WHERE user_id = ?",
                    user_id
                )
            
            flash("Faculty details updated successfully!", "success")

        except Exception as e:
            flash(f"Error updating: {e}", "danger")
            print(f"Error updating faculty list: {e}")

        return redirect(url_for('faculty_management'))
    
    else:
        curr_settings_row = db.execute("SELECT academic_session, academic_term FROM drive_settings")
        if not curr_settings_row:
            print("Please configure batch settings in batch management before opening faculty_management")
            flash("Please configure batch settings in batch management", "warning")
            redirect(request.referrer)
        
        curr_academic_session = curr_settings_row[0]["academic_session"]
        curr_academic_term = curr_settings_row[0]["academic_term"]

        semester = get_sem_options([curr_academic_session], [curr_academic_term])
        branches = get_branch_options([curr_academic_session], [curr_academic_term])
        sections = get_section_options([curr_academic_session], [curr_academic_term])

        coordinator_list = db.execute("SELECT * FROM faculty_details WHERE is_coordinator=1")
        
        faculty_data = db.execute("SELECT * FROM faculty_details")
        return render_template("faculty_management.html", 
        faculty_data=faculty_data,
        semester=semester,
        branches=branches,
        sections=sections,
        coordinator_list=coordinator_list
        )

@app.route("/delete_user/<pk>", methods=["POST"])
@login_required
def delete_user(pk):
    user_role = session.get("user_role")
    if user_role != "admin" and user_role != "coordinator":
        abort(404)

    key_to_delete = request.form.get("college_email")
    if pk == 'faculty':
        if not key_to_delete:
            flash("Error: No faculty email was provided for deletion.", "danger")
            return redirect(url_for("faculty_management"))

        try:
            # Execute the DELETE query using the primary key(college email)
            db.execute("DELETE FROM faculty_details WHERE college_email = ?", key_to_delete)
            flash(f"Successfully deleted faculty member: {key_to_delete}", "success")
            update_faculty_emails()
                
        except Exception as e:
            # Log the error and show a generic message
            print(f"Database error while deleting faculty: {e}", file=sys.stderr)
            flash("An error occurred while trying to delete the faculty member.", "danger")

        return redirect(url_for("faculty_management"))
    
    elif pk == 'student':
        if not key_to_delete:
            flash("Error: No Student email was provided for deletion.", "danger")
            return redirect(url_for("student_management_page"))

        try:
            # Execute the DELETE query using the primary key(college email)
            db.execute("DELETE FROM users WHERE email = ?", key_to_delete)
            flash(f"Successfully deleted student: {key_to_delete}", "success")
        except Exception as e:
            # Log the error and show a generic message
            print(f"Database error while deleting student: {e}", file=sys.stderr)
            flash("An error occurred while trying to delete the student.", "danger")

        return redirect(url_for("student_management_page"))

@app.route("/uploadExcel", methods=["POST"])
def uploadExcel():
    user_role = session.get("user_role")
    if user_role != "admin" and user_role != "coordinator":
        abort(404)

    facutly_data = request.files.get('uploadedExcelFile')
    if not facutly_data or facutly_data.filename == '':
        return "No file selected or invalid file", 400

    try:
        # Check the filename to decide which pandas function to use
        filename = facutly_data.filename.lower()
        
        if filename.endswith('.csv'):
            # Read as CSV
            df = pd.read_csv(facutly_data)
        else:
            # Read as Excel (default for .xlsx, .xls)
            df = pd.read_excel(facutly_data)

        # Clean up column names (CRITICAL step for matching SQL names)
        # This ensures 'Full Name' becomes 'full_name', 'College Email' becomes 'college_email'
        df.columns = df.columns.str.lower().str.replace(' ', '_').str.strip()

        # Define the columns that MUST have data
        compulsory_cols = ['college_email', 'full_name', 'designation', 'department']
        
        # A. Check if the columns exist in the file
        missing_cols = [col for col in compulsory_cols if col not in df.columns]
        if missing_cols:
            flash(f"Upload Failed: The file is missing these required columns: {', '.join(missing_cols)}", "danger")
            return redirect(url_for("faculty_management"))

        # B. Check for Null/Empty values in these columns
        # First, convert pure whitespace strings to NaN (null) so we can catch them
        # (regex=True allows checking for strings that are just spaces)
        df[compulsory_cols] = df[compulsory_cols].replace(r'^\s*$', pd.NA, regex=True)

        # Check if any row has a null value in the compulsory columns
        if df[compulsory_cols].isnull().any().any():
            # Find the rows that have missing data
            invalid_rows = df[df[compulsory_cols].isnull().any(axis=1)]
            
            # Get the Excel row numbers (Index starts at 0, +2 accounts for 0-index and Header row)
            error_row_numbers = (invalid_rows.index + 2).tolist()
            
            flash(f"Upload Failed: Missing compulsory details (Name, Email, Designation, or Dept) on Excel rows: {error_row_numbers[:10]}{'...' if len(error_row_numbers) > 10 else ''}. Please fix and try again.", "danger")
            return redirect(url_for("faculty_management"))
        
        # Convert emails to string, lower and strip any leading/trailing space 
        df['college_email'] = df['college_email'].astype(str).str.lower().str.strip()

        print("emails data simplified")

        # Verify faculty email is of SKIT domain
        invalid_emails_df = df[~df['college_email'].str.endswith('@skit.ac.in')] 
        if not invalid_emails_df.empty:
            bad_email_list = invalid_emails_df['college_email'].tolist()
            flash(f"Upload Failed: Found {len(bad_email_list)} invalid emails. All emails must end with @skit.ac.in. Examples: {bad_email_list[:3]}", "danger")
            return redirect(url_for("faculty_management"))
        
        print("Checked for invalid emails")

        # Replace NaN (Not a Number) with None (which becomes NULL in SQL)
        df = df.where(pd.notnull(df), None)

        print("Converted Nan to None")

        # Convert data frame to list of dictionaries
        rows_to_insert = df.to_dict(orient='records')

        for row in rows_to_insert:

            contact_val = row.get("contact")
            if not contact_val: # This catches None and empty strings
                contact_val = 'to be updated'
                
            db.execute("""
                INSERT INTO faculty_details (
                    college_email, full_name, designation, department, contact
                ) VALUES (?,?,?,?,?)
                ON CONFLICT(college_email) DO UPDATE SET
                    full_name = excluded.full_name,
                    designation = excluded.designation,
                    department = excluded.department,
                    contact = excluded.contact
            """,
            row.get("college_email"),
            row.get("full_name"),
            row.get("designation"),
            row.get("department"),
            contact_val
            )

        flash("Data updated successfully!","success")

    except Exception as e:
        flash(f"Data import failed. Check if table name/columns match. Error: {e}")
        print(f"Insertion Error: {e}")

    update_faculty_emails()

    return redirect(url_for('faculty_management'))

@app.route("/assign_batch", methods=["POST"])
@login_required
def assign_batch():
    user_role = session.get("user_role")

    if user_role != "admin" and user_role != "coordinator":
        abort(404)
    
    college_email = request.form.get("college_email")
    semester = request.form.get("semester_option")
    branch = request.form.get("branch_option")
    section = request.form.get("section_option")

    try:
        # Update batch in database
        db.execute("UPDATE faculty_details SET semester=?, branch=?, section=? WHERE college_email=?",
                semester, branch, section, college_email)
        flash("Batch updated!", "success")

    except Exception as e:
        flash(f"Error updating: {e}", "danger")
    
    return redirect (url_for("faculty_management"))
    
@app.route("/discharge_faculty", methods=["POST"])
@login_required
def discharge_faculty():
    user_role = session.get("user_role")

    if user_role != "admin" and user_role != "coordinator":
        abort(404)

    faculty_email = request.form.get("college_email")
    try:
        db.execute(
            "UPDATE faculty_details SET semester=NULL, branch=NULL, section=NULL WHERE college_email=?",
            faculty_email
            )
        flash(f"Faculty with email {faculty_email} was discharged.", "success")
        update_faculty_emails()

    except Exception as e:
        flash(f"An unexpected database error occured. Please contact Admin.", "danger")
        print(f"Error at updating faculty emails: {e}")

    return redirect(url_for("faculty_management"))

@app.route("/add_coordinator", methods=["POST"])
@login_required
def add_coordinator():
    user_role = session.get("user_role")
    if user_role != "admin":
        abort(404)

    try:
        to_be_coordinator_email = request.form.get("college_email")

        db.execute("UPDATE users SET role='coordinator' WHERE email=?", to_be_coordinator_email)
        db.execute("UPDATE faculty_details SET is_coordinator=1 WHERE college_email=?", to_be_coordinator_email)

        flash(f"Assigned {to_be_coordinator_email} as SODECA Coordinator", "success")

    except Exception as e:
        print(f"Database Error: {e}")
        flash("Database Error", "danger")
    return redirect(url_for("faculty_management"))

@app.route("/discharge_coordinator", methods=["POST"])
@login_required
def discharge_coordinator():
    user_role = session.get("user_role")
    if user_role != "admin":
        abort(404)

    try:
        to_be_discharged = request.form.get("college_email")

        db.execute("UPDATE users SET role='faculty' WHERE email=?", to_be_discharged)
        db.execute("UPDATE faculty_details SET is_coordinator=0 WHERE college_email=?", to_be_discharged)

        flash(f"Dischared {to_be_discharged} as SODECA Coordinator", "success")

    except Exception as e:
        print(f"Database Error: {e}")
        flash("Database Error", "danger")

    return redirect(url_for("faculty_management"))

@app.route("/student_report", methods=["GET", "POST"])
@login_required
def student_report():
    user_role = session.get("user_role")
    if user_role != 'admin' and user_role != 'coordinator':
        abort(404)

    current_session_row = db.execute("SELECT academic_session FROM drive_settings")
    if not current_session_row:
        flash("Configure batch settings in batch management","warning")
        return redirect(request.referrer)

    current_session = current_session_row[0]['academic_session']

    # Queries as per the number of forms selected
    base_queries = []

    # If applied filter
    if request.method == "POST":

        # where_clause will have parameter inputs
        where_params = []
        where_clause = ""
        filtered_data = []
        received_json_data = request.get_json()
        print("Received JSON Data is: ",received_json_data)
        academic_session = received_json_data.get('academic_session_data')
        print("Academic session are: ",academic_session)
        if academic_session:
            where_params.append(f"f.academic_session IN ('{academic_session}')")
        
        academic_term = received_json_data.get('even_odd_data')
        print("Academic terms are: ",academic_term)
        if academic_term:
            where_params.append(f"f.academic_term IN ('{academic_term}')")

        # Get multiple checkbox values using .getlist()
        semesters = received_json_data.get('semester_data') # Returns a list like ['1', '3', '5']
        print("Semesters are: ",semesters)
        if semesters:
            joined_semesters = ",".join(semesters)
            where_params.append(f"f.sem IN ({joined_semesters})")

        branches = received_json_data.get('branch_data')   # Returns a list like ['CSE', 'IT']
        print("Branches are: ",branches)
        if branches:
            quoted_branches = [f"'{branch}'" for branch in branches]
            joined_branches = ",".join(quoted_branches)
            where_params.append(f"f.branch IN ({joined_branches})")
        
        sections = received_json_data.get('section_data')
        print("Sections are: ",sections)
        if sections:
            quoted_sections = [f"'{section}'" for section in sections]
            joined_sections = ",".join(quoted_sections)
            where_params.append(f"f.section IN ({joined_sections})")

        submission_category = received_json_data.get('submission_type_data')
        print("Submission categories are: ",submission_category)
        if submission_category:
            where_params.append(f"f.submission_category IN ('{submission_category}')")

        # Update where_clause with available inputs 
        where_clause = " AND ".join(where_params) if where_params else "1=1"

        forms = received_json_data.get('form_type_data')
        print("Forms are: ",forms)
        if forms:
            for form in forms:
                base_queries.append(
                    f"""SELECT s.student_name, s.university_roll_no, '{form}' AS category, f.entry_id, f.google_file_id, f.submitted_at, 
                    f.withdrawn_at, f.status, f.certificate, f.sem, f.branch, f.section, f.academic_session, f.academic_term
                    FROM student_details s INNER JOIN {form} f ON s.student_user_id = f.student_id WHERE {where_clause}"""
                    )
        else:
            for form in form_name_list:
                base_queries.append(
                f"""SELECT s.student_name, s.university_roll_no, '{form}' AS category, f.entry_id, f.google_file_id, f.submitted_at, 
                f.withdrawn_at, f.status, f.certificate, f.sem, f.branch, f.section, f.academic_session, f.academic_term
                FROM student_details s INNER JOIN {form} f ON s.student_user_id = f.student_id WHERE {where_clause}"""
                )

        if base_queries:
            complete_query = " UNION ALL ".join(base_queries)
            
            final_query = f"{complete_query} ORDER BY submitted_at DESC"

            try:
                print(f"Executing query: {final_query}")  # Debug
                filtered_data = db.execute(final_query)
                print("Final filtered data is: ",filtered_data)
                return jsonify({"success": True, "message": "All Ok!", "data": filtered_data}), 200

                if not filtered_data:
                    flash("No records found with selected filters.", "info")
            
            except Exception as e:
                flash(f"Database error: {e}", "danger")
                print(f"Error: {e}")
                print(f"Query: {final_query}")  # See the actual query
                return jsonify({"success": False, "message": "We are experiencing technical difficulties. Please try again later."}), 500
        else:
            flash("Please select at least one form to filter.", "warning")

        return jsonify({"success": False, "message": "Something went wrong. Please try again later."}), 500
    else:
        # Without filter
        for form in form_name_list:
            base_queries.append(
                f"""SELECT s.student_name, s.university_roll_no,
                '{form}' AS category, f.entry_id, f.google_file_id, f.submitted_at, f.withdrawn_at , f.status, f.certificate,
                f.sem, f.branch, f.section, f.academic_session, f.academic_term
                FROM student_details s INNER JOIN {form} f ON s.student_user_id = f.student_id WHERE academic_session='{current_session}'"""
                )

        complete_query = " UNION ALL ".join(base_queries) 
        final_query = f"{complete_query} ORDER BY submitted_at DESC"
        filtered_data = db.execute(final_query)

    academic_session_list = db.execute("SELECT DISTINCT academic_session FROM batch_structure")
    sem_options_list = get_sem_options()
    branch_options_list = get_branch_options()
    section_options_list = get_section_options()

    return render_template("student_report.html", 
        filtered_data=filtered_data, 
        form_dict=form_dict,
        academic_session_list=academic_session_list,
        sem_options_list=sem_options_list,
        branch_options_list=branch_options_list,
        section_options_list=section_options_list,
        current_session=current_session
    )

@app.route("/download_proof_files", methods=["POST"])
@login_required
def download_proof_files():
    user_role = session.get("user_role")
    if user_role != 'admin' and user_role != 'coordinator':
        print(user_role)
        abort(404)

    data = request.get_json()
    filenames = data.get("filenames", [])

    upload_dir = app.config["UPLOAD_FOLDER"]
    memory_file = io.BytesIO()

    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename in filenames:
            # Join UPLOAD_FOLDER path with filename
            file_path = os.path.join(upload_dir, filename)

            if os.path.exists(file_path):
                # Write file inside zip archive
                zf.write(file_path, arcname=filename)

    memory_file.seek(0)

    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name="filtered_proofs.zip",
    )

@app.route("/batch_management", methods=["GET"])
@login_required
def batch_management():
    user_role = session.get("user_role")

    if user_role != "admin" and user_role != "coordinator":
        abort(404)
    
    # get the current drive settings stored in db
    row = db.execute("SELECT * FROM drive_settings WHERE id=1")
    drive_settings = row[0] if row else {}

    batch_rows = []
    if drive_settings:
        batch_rows = db.execute("SELECT * FROM batch_structure WHERE academic_session = ? AND academic_term = ?",
        drive_settings['academic_session'], drive_settings['academic_term'])

    current_year = datetime.now().year

    session_options = [f"{current_year-1}-{(current_year)%100}", 
    f"{current_year}-{(current_year+1)%100}", 
    f"{current_year+1}-{(current_year+2)%100}"]

    return render_template("batch_management.html", 
    drive_settings=drive_settings,
    batch_rows=batch_rows,
    session_options=session_options)

# Handles student_management_page loading and excel file uploads
@app.route("/student_management_page", methods=["GET", "POST"])
@login_required
def student_management_page():
    user_role = session.get("user_role")
    if user_role != "admin" and user_role != "coordinator":
        abort(404)

    if request.method == 'POST':
        new_data = request.files.get('excel_file')
        if not new_data or new_data.filename == '':
            flash('No file is selected or invalid file',"info")
            return "No file selected or invalid file", 400

        df = pd.read_excel(new_data, engine="openpyxl")

        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        invalid_emails_df = df[~df['email'].str.strip().str.endswith('@skit.ac.in')]
        if not invalid_emails_df.empty:
            bad_email_list = invalid_emails_df['email'].tolist()
            flash(
                f"Upload Failed: Found {len(bad_email_list)} invalid emails. All emails must end with @skit.ac.in. Examples: {bad_email_list[:3]}",
                "danger")
            return redirect(url_for("student_management_page"))
        rows_to_insert = df.to_dict(orient="records")
        for data in rows_to_insert:
            email = data.get("email")
            db.execute("""
                INSERT INTO users (
                    email
                ) VALUES (?)
            """, email)

        flash('We are glad to share that your excel file is uploaded successfully!',"success")
        return redirect(url_for('student_management_page'))
    else:
        student_email_list = db.execute(
            "SELECT email FROM users WHERE role = 'student'"
        )
        student_list = []
        for row in student_email_list:
            student_list.append({'email': row["email"],'val': db.execute(
                """SELECT * FROM student_details 
                WHERE student_details.student_user_id = (
                SELECT user_id FROM users WHERE email = ?
                )""",
                row["email"]
            )})
        return render_template('student_management_page.html', student_list=student_list)
    
# Handles add email feature in student_management_page
@app.route("/add_email", methods=["POST"])
@login_required
def addEmail():
    user_role = session.get("user_role")
    if user_role != "admin" and user_role != "coordinator":
        abort(404)

    email = request.form.get("new_email")
    existing_email = db.execute(
        "SELECT email FROM users"
    )
    for emails in existing_email:
        if emails["email"] == email:
            flash("Email already exists!","danger")
            return redirect(url_for('student_management_page'))
        elif not str(email).lower().endswith('@skit.ac.in'):
            flash("Only institutional mails are allowed!", "danger")
            return redirect(url_for('student_management_page'))
    db.execute("""
        INSERT INTO users (
            email, auth_provider
        ) VALUES (?, ?)
    """, email, 'admin')    
    
    flash(f"User added successfully!", "success")

    return redirect(url_for('student_management_page'))

@app.route('/update_drive_settings', methods=["POST"])
@login_required
@drive_auth_required
def update_drive_master_folder():
    user_role = session.get("user_role")
    if user_role != "admin" and user_role != "coordinator":
        abort(404)

    # 1. Check if we have the drive token
    token = session.get('drive_auth_token')
    if not token:
        flash("Please authorize google drive", "warning")
        return redirect(url_for("batch_management"))

    try:
        # Build the Drive Service using the token
        creds = Credentials(
            token=token.get('access_token'),
            refresh_token=token.get('refresh_token'),
            token_uri=app.config.get('GOOGLE_TOKEN_URI', 'https://oauth2.googleapis.com/token'),
            client_id=app.config['DRIVE_CLIENT_ID'],
            client_secret=app.config['DRIVE_CLIENT_SECRET'],
            scopes=token.get('scope', [])
        )
        
        service = build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"Error building drive service: {e}")
        flash("Google drive error", "danger")
        return redirect(url_for("batch_management"))


    academic_session = request.form.get("academic_session")
    academic_term = request.form.get("academic_term")
    folder_name = request.form.get("folder_name")
    # Create a new master folder or just return the existing folder's id
    master_folder_id = get_or_create_folder(service, folder_name)
    if (master_folder_id):
        master_folder_link = f"https://drive.google.com/drive/folders/{master_folder_id}"
    else:
        flash("Error: Creating/Updating Master drive folder", "danger")
        return redirect(url_for("batch_management"))

    # Create folders named participations and achievement
    participation_folder_id = get_or_create_folder(service, "participation", master_folder_id)
    if (participation_folder_id):
        participation_folder_link = f"https://drive.google.com/drive/folders/{participation_folder_id}"
    else:
        flash("Error: Creating participation drive folder, please create again", "danger")
        return redirect(url_for("batch_management"))
    achievement_folder_id = get_or_create_folder(service, "achievement", master_folder_id)
    if (achievement_folder_id):
        achievement_folder_link = f"https://drive.google.com/drive/folders/{achievement_folder_id}"
    else:
        flash("Error: Creating achievement drive folder, please create again", "danger")
        return redirect(url_for("batch_management"))

    try: 
        db.execute("""
                INSERT INTO drive_settings (id, academic_session, academic_term, master_folder_link, master_folder_id, 
                participation_folder_link, participation_folder_id, achievement_folder_link, achievement_folder_id, updated_on) 
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '+5 hours', '+30 minutes')) 
                ON CONFLICT (id) DO UPDATE SET
                    academic_session = excluded.academic_session,
                    academic_term = excluded.academic_term,
                    master_folder_link = excluded.master_folder_link,
                    master_folder_id = excluded.master_folder_id,
                    participation_folder_link = excluded.participation_folder_link,
                    participation_folder_id = excluded.participation_folder_id,
                    achievement_folder_link = excluded.achievement_folder_link,
                    achievement_folder_id = excluded.achievement_folder_id,
                    updated_on = datetime('now', '+5 hours', '+30 minutes')
            """, academic_session, academic_term, master_folder_link, master_folder_id, 
            participation_folder_link, participation_folder_id, achievement_folder_link, achievement_folder_id)
        print("System settings and Master folder updated")
        flash("System settings and Master folder updated!", "success")

    except Exception as e:
        print(f"db erorr: {e}")        
        flash(f"Database error: {e}", "danger")

    return redirect(url_for("batch_management"))

@app.route('/create_drive_structure', methods=["POST"])
@login_required
@drive_auth_required 
def create_drive_structure():
    user_role = session.get("user_role")
    if user_role != "admin" and user_role != "coordinator":
        abort(404)

    # 1. Check if we have the token from Step 1
    token = session.get('drive_auth_token')
    if not token:
        flash("Please authorize Google Drive first.", "warning")
        return redirect(url_for('batch_management'))
    
    sys_config_dict = db.execute("SELECT master_folder_id FROM drive_settings WHERE id=1")
    if sys_config_dict:
        sys_config = sys_config_dict[0]
        master_folder_id = sys_config["master_folder_id"]
        if not master_folder_id:
            flash("Kindly create a drive master folder before updating the structure", "warning")
            return redirect(url_for("batch_management"))

    curr_academic_session = ""
    curr_academic_term = ""
    curr_settings_row = db.execute("SELECT academic_session, academic_term FROM drive_settings")
    if (curr_settings_row):
        curr_settings = curr_settings_row[0]
        curr_academic_session = curr_settings['academic_session']
        curr_academic_term = curr_settings['academic_term']
    else:
        flash("Please update the drive master folder, before updating batch structure", "warning")
        return redirect("batch_management")

    # Get drive structure inputs
    raw_batch_structure = request.form.get("structure_json")
    # Guard against None or empty string before parsing
    if not raw_batch_structure:
        return "Missing structure configuration payload", 400
    try:
        batch_structure = json.loads(raw_batch_structure)
    except (json.JSONDecodeError, TypeError):
        return "Malformed configuration layout JSON received", 400

    try:
        # 1. Build the Drive Service using the token
        # We assume the token in session has what we need
        creds = Credentials(
            token=token.get('access_token'),
            refresh_token=token.get('refresh_token'),
            token_uri=app.config.get('GOOGLE_TOKEN_URI', 'https://oauth2.googleapis.com/token'),
            client_id=app.config['DRIVE_CLIENT_ID'],
            client_secret=app.config['DRIVE_CLIENT_SECRET'],
            scopes=token.get('scope', [])
        )
        
        service = build('drive', 'v3', credentials=creds)
    except Exception as e:
        flash (f"Google Drive Service Error: {e}", "danger")
        print(e)
        return redirect("batch_management.html")
    
    try:
        # 1. Open the transaction manually
        db.execute("BEGIN TRANSACTION")
        
        # 2. Track what we insert so we don't clear the structure table prematurely
        structures_to_insert = []
        sem_list = set()
        branch_list = set()
        
        for batch in batch_structure:
            sem = batch["sem"]
            sem_folder_id = get_or_create_folder(service, sem, master_folder_id)
            
            if sem_folder_id:
                branch = batch["branch"]
                branch_folder_id = get_or_create_folder(service, branch, sem_folder_id)

                if branch_folder_id:
                    section_list = [s.strip() for s in batch["section"].split(',') if s.strip()]
                    
                    for section in section_list:
                        section_folder_id = get_or_create_folder(service, section, branch_folder_id)

                        if section_folder_id:
                            structures_to_insert.append((sem, branch, section))
                            sem_list.add(sem)
                            branch_list.add(branch)

                            for form_name, form_title in form_dict.items():
                                form_folder_id = get_or_create_folder(service, form_title, section_folder_id)

                                if form_folder_id:
                                    folder_map_id = f"{sem}_{branch}_{section}_{form_name}"

                                    db.execute("""
                                            INSERT INTO drive_folder_map (id, drive_folder_id, semester, branch, section, form_name) 
                                            VALUES (?, ?, ?, ?, ?, ?) 
                                            ON CONFLICT (id) DO UPDATE SET
                                                drive_folder_id = excluded.drive_folder_id 
                                        """, folder_map_id, form_folder_id, sem, branch, section, form_name)

        # 3. Apply the layout changes at the very end
        if structures_to_insert:
            db.execute("""
                DELETE FROM batch_structure WHERE academic_session = ? AND academic_term = ?
            """, curr_academic_session, curr_academic_term)
            # However, because we are inside a single transaction, looping individual executions is incredibly fast!
            for item in structures_to_insert:
                db.execute("""
                    INSERT INTO batch_structure (sem, branch, section, academic_session, academic_term)
                    VALUES (?, ?, ?, ?, ?)
                """, item[0], item[1], item[2], curr_academic_session, curr_academic_term)

        if sem_list and branch_list:
            db.execute("DELETE FROM batch_structure_summary")
            sem_list_str = ",".join(str(s) for s in sorted(sem_list))
            branch_list_str = ",".join(sorted(branch_list))

            db.execute("""
                    INSERT INTO batch_structure_summary (id, sem_list, branch_list, updated_on)
                    VALUES (1, ?, ?, datetime('now', '+5 hours', '+30 minutes'))
                    ON CONFLICT (id) DO UPDATE SET
                        sem_list = excluded.sem_list,
                        branch_list = excluded.branch_list,
                        updated_on = excluded.updated_on
                """, sem_list_str, branch_list_str)

        # 4. Commit everything if loops completed flawlessly
        db.execute("COMMIT")
        flash("Drive structure sync complete!", "success")

    except Exception as e:
        # Roll back all changes instantly if an unhandled error/crash happens inside the transaction
        print(f"Structure creation failed: {e}")
        flash(f"An error occurred: {e}", "danger")
        try:
            db.execute("ROLLBACK")
        except Exception:
            pass

    return redirect(url_for('super_admin'))

@app.route("/update_master_folder", methods=["POST"])
@login_required
def update_master_folder():
    user_role = session.get("user_role")
    if user_role != "admin" and user_role != "coordinator":
        abort(404)

    folder_link = request.form.get("new_master_link")
    if not folder_link:
        flash("Please paste the drive folder link.")
        return redirect("/batch_management")
    
    folder_id = get_folder_id(folder_link)

    db.execute("""
        INSERT INTO drive_settings (id, master_folder_link, master_folder_id)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET 
        master_folder_link = excluded.master_folder_link,
        master_folder_id = excluded.master_folder_id
    """, folder_link, folder_id)

    flash("Master folder link updated!", "success")
    return redirect(url_for("batch_management"))    

@app.route("/dev_management", methods=["GET","POST"])
@login_required
def dev_management():
    # Add an email
    if request.method == "POST":
        dev_email = request.form.get("dev_email")
        if not dev_email:
            flash("Email is required.", "danger")
            return redirect(url_for("dev_management"))
        
        row = db.execute("SELECT email FROM users WHERE email=?", dev_email)
        if len(row) == 1:
            flash("Email already exists as a developer.", "info")
            return redirect(url_for("dev_management"))
        
        try:
            # Add email in users table and assign role = "dev"
            db.execute("INSERT INTO users(email, role) VALUES(?,?)", dev_email, "dev")
            flash(f"Successfully added {dev_email} as a developer", "success")

        except Exception as e:
            flash(f"An unexpected database error occured.", "danger")
            print(f"Error at updating dev emails: {e}")
        
        return redirect(url_for("dev_management"))
    else:
        dev_emails = db.execute("SELECT email FROM users WHERE role='dev'")
        return render_template("dev_management.html", dev_emails=dev_emails)

@app.route("/remove_dev", methods=["POST"])
def remove_dev():
    if request.method == "POST":
        dev_email = request.form.get("dev_email")

        try:
            db.execute("DELETE FROM users WHERE email=?", dev_email)

        except Exception as e:
            flash(f"Removal failed, an unexpected error occured.", "danger")
            print(f"Error at updating dev emails: {e}")

        return redirect(url_for("dev_management"))

@app.route("/visual_report", methods=["POST"])
def visual_report():

    chartData = []
    chartLabels = []

    for form_name, form_title in form_dict.items():
        val = None
        if session.get('user_role') == 'admin':
            query = f"SELECT COUNT(*) FROM {form_name}"
            val = db.execute(query)
        elif session.get('user_role') == 'faculty':
            batch_details = session.get("batch_details")

            query = f"""SELECT COUNT(*) FROM {form_name} as f
                                    INNER JOIN student_details as s 
                                    ON f.student_id = s.student_user_id
                                    WHERE s.branch=? AND 
                                    s.semester=? AND 
                                    s.section=?"""
            val = db.execute(query,
                             batch_details["branch"],
                             batch_details["semester"],
                             batch_details["section"])

        if val and val[0]['COUNT(*)'] != 0:
            chartData.append(val[0]['COUNT(*)'])
            chartLabels.append(form_title)

    return jsonify({"chartData" : chartData, "labelData": chartLabels})

if __name__ == '__main__':

    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    if not os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'w') as f:
            pass

    app.run(host="0.0.0.0", debug=True)