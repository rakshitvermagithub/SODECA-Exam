import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER')
    ALLOWED_EXTENSIONS = {'pdf'}
    DATABASE_FILE = os.getenv('DATABASE_FILE')
    SECRET_KEY = os.getenv('SECRET_KEY')

    # Session configuration
    SESSION_PERMANENT = False
    SESSION_TYPE = "filesystem"

    # Session security settings
    SESSION_COOKIE_SECURE = False     # Only send cookies over HTTPS(false for development only!)
    SESSION_COOKIE_HTTPONLY = True    # Prevent XSS attacks
    SESSION_COOKIE_SAMESITE = 'Lax'   # CSRF protection
    SESSION_COOKIE_NAME = 'session'   # Custom session cookie name
    # Additional session security
    SESSION_COOKIE_MAX_AGE = 3600  # Session expires in 1 hour
    PERMANENT_SESSION_LIFETIME = 3600  # Same as above
    
    # OAuth credentials
    GOOGLE_CLIENT_ID = os.getenv('OAUTH_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.getenv('OAUTH_CLIENT_SECRET')
