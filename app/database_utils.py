import os
from app.models import *
from app import db


def import_csvs(rootdir='testcases/test_case1'):
    for subdir, dirs, files in os.walk(rootdir):
        for file in files:
            path = os.path.join(subdir, file)
            if file == 'courses.csv':
                Course.load_csv(path)
            elif file == 'instructors.csv':
                Instructor.load_csv(path)
            elif file == 'listings.csv':
                Listing.load_csv(path)
            elif file == 'prereqs.csv':
                Prereq.load_csv(path)
            elif file == 'programs.csv':
                Program.load_csv(path)
            elif file == 'records.csv':
                AcademicRecord.load_csv(path)
            elif file == 'requests.csv':
                Request.load_csv(path)
            elif file == 'students.csv':
                Student.load_csv(path)


def clear_db():
    db.drop_all()
    db.create_all()
