from pathlib import Path
import os
from dotenv import load_dotenv

# Automatically load environment variables from backend/.env
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

from .base import *

DEBUG = True

# Hook PyMySQL as the MySQLdb driver
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass

# Allow fallback to SQLite for local standalone testing without Docker MySQL
if os.getenv('USE_SQLITE', 'False').lower() in ('true', '1', 'yes'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Execute Celery tasks eagerly in development when Redis is not running locally
CELERY_TASK_ALWAYS_EAGER = os.getenv('CELERY_TASK_ALWAYS_EAGER', 'True').lower() in ('true', '1', 'yes')
CELERY_TASK_EAGER_PROPAGATES = True

# Disable strict password validation in development
AUTH_PASSWORD_VALIDATORS = []
