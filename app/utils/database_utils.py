import os
from app.models import *
from app import db
from io import StringIO

file_name_switcher = {
    'courses.csv': Course,
    'instructors.csv': Instructor,
    'listings.csv': Listing,
    'prereqs.csv': Prereq,
    'programs.csv': Program,
    'records.csv': AcademicRecord,
    'students.csv': Student
}


def get_load_function(filename, exclusions=None):
    if filename[:8] == 'requests':
        return Request
    elif filename in file_name_switcher and (exclusions is None or filename not in exclusions):
        return file_name_switcher[filename]
    return None


def import_csv_by_file(file, connection=None):
    if file.filename in file_name_switcher:
        # load files into database after conversion from binary files to text-mode files
        get_load_function(file.filename).load_csv_by_file(StringIO(file.read().decode(), newline=None), connection)


def import_csvs_by_filepath(rootdir='app/static/testcases/test_case1', exclusions=None):
    # TODO: handle requestsx.csv, where x is the sequence number of the request file
    with db.engine.begin() as connection:
        if environ.get('IS_HEROKU'):
            connection.execute("SET CONSTRAINTS ALL DEFERRED")
        for subdir, dirs, filenames in os.walk(rootdir):
            for filename in filenames:
                path = os.path.join(subdir, filename)
                func = get_load_function(filename, exclusions=exclusions)
                if func:
                    func.load_csv(path, connection)


def clear_db():
    db.drop_all()
    db.create_all()

def defer_constraints(connection):
    if environ.get('IS_HEROKU'):
        connection.execute("SET CONSTRAINTS ALL DEFERRED")
    else:
        connection.execute('PRAGMA defer_foreign_keys=ON')
