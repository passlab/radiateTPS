import os
from pathlib import Path

# Base directory
basedir = Path(__file__).parent.parent

class Config:
    """Base config."""
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.getenv("SECRET_KEY", "your_default_secret_key")
    ##set API key as environment variable and access here
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        f'sqlite:///{basedir / "radiate_tps.db"}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File upload configuration
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB max file size
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    OUTPUT_FOLDER = os.path.join(basedir, 'Output')
    
    # Ensure directories exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

class DevelopmentConfig(Config):
    """Development environment config."""
    DEBUG = True

class ProductionConfig(Config):
    """Production environment config."""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')  # Use environment variable in production

# Default config
config = DevelopmentConfig  # Change this for production
