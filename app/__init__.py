from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from os import environ
from flask_wtf import CSRFProtect

app = Flask(__name__)
csrf = CSRFProtect(app)

if environ.get('IS_HEROKU'):
    app.config.from_object('config.ProductionConfig')
else:
    app.config.from_object('config.DevelopmentConfig')

db = SQLAlchemy(app)

from sqlalchemy.engine import Engine
from sqlalchemy import event


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if not environ.get('IS_HEROKU'):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


from app import views, models
from app.database_utils import *
