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
    'requests.csv': Request,
    'students.csv': Student
}

def validate_csv(filename, exclusions=None):
    return filename in file_name_switcher and (exclusions is None or filename not in exclusions)


def import_csv(file, connection=None):
    if file.filename in file_name_switcher:
        # load files into database after conversion from binary files to text-mode files
        file_name_switcher[file.filename].load_csv_by_file(StringIO(file.read().decode(), newline=None), connection)


def import_csvs(rootdir='testcases/test_case1', connection=None, exclusions={'requests.csv'}):
    # TODO: handle requestsx.csv, where x is the sequence number of the request file

    for subdir, dirs, files in os.walk(rootdir):
        for file in files:
            path = os.path.join(subdir, file)

            if validate_csv(file, exclusions={'requests.csv'}):
                file_name_switcher[file].load_csv(path, connection)


def clear_db():
    db.drop_all()
    db.create_all()
