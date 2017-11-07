from app import db
from sqlalchemy.types import *
from sqlalchemy import ForeignKey, UniqueConstraint, PrimaryKeyConstraint
from sqlalchemy.ext.declarative import declared_attr
from flask import session
import csv


class MyMixin(object):
    @classmethod
    def parse_csv_by_file(cls, f):
        pass

    @classmethod
    def parse_csv(cls, csv_filepath):
        with open(csv_filepath) as csv_file:
            for row in cls.parse_csv_by_file(csv_file):
                yield row

    @classmethod
    def load_csv_helper(cls, csv_reader_generator):
        rows = []
        for row in csv_reader_generator:

            # TODO: remove after login/registration implemented
            if 'user_id' not in session:
                session['user_id'] = 1

            row['user_id'] = session['user_id']
            rows.append(row)
        db.engine.execute(
            cls.__table__.insert(),
            rows,
            autocommit=True)

    @classmethod
    def load_csv(cls, csv_filepath):
        cls.load_csv_helper(cls.parse_csv(csv_filepath))

    @classmethod
    def load_csv_by_file(cls, f):
        cls.load_csv_helper(cls.parse_csv_by_file(f))


class Course(db.Model, MyMixin):
    user_id = db.Column(Integer)
    id = db.Column(Integer)
    name = db.Column(String(255), unique=True, nullable=False)
    cost = db.Column(Integer, nullable=False)
    PrimaryKeyConstraint(user_id, id)

    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            yield {'id': row[0], 'name': row[1], 'cost': row[2]}


class Prereq(db.Model, MyMixin):
    user_id = db.Column(Integer)
    course_id = db.Column(Integer, ForeignKey(Course.id), nullable=False)
    prereq_id = db.Column(Integer, ForeignKey(Course.id), nullable=False)
    PrimaryKeyConstraint(user_id, course_id, prereq_id)

    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            yield {'course_id': row[0], 'prereq_id': row[1]}


class Instructor(db.Model, MyMixin):
    user_id = db.Column(Integer)
    id = db.Column(Integer)
    name = db.Column(String(255), nullable=False)
    office_hours = db.Column(String(255), nullable=False)
    email = db.Column(String(255), nullable=False)
    # NOTE: can't be unique as = 0 when instructor not teaching course
    course_id = db.Column(Integer, ForeignKey(Course.id), nullable=False)
    PrimaryKeyConstraint(user_id, id)

    # @classmethod
    # def parse_csv_by_file(cls, f):
    #     reader = csv.reader(f, delimiter=',')
    #     for row in reader:
    #         yield {'id': row[0], 'name': row[1], 'office_hours': row[2], 'email': row[3], 'course_id': row[4]}

    # course_id ignored for now in initial csv import
    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            yield {'id': row[0], 'name': row[1], 'office_hours': row[2], 'email': row[3], 'course_id': 0}


class Program(db.Model, MyMixin):
    user_id = db.Column(Integer)
    id = db.Column(Integer)
    name = db.Column(String(255), unique=True, nullable=False)
    PrimaryKeyConstraint(user_id, id)

    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            yield {'id': row[0], 'name': row[1]}


class Student(db.Model, MyMixin):
    user_id = db.Column(Integer)
    id = db.Column(Integer)
    name = db.Column(String(255), nullable=False)
    address = db.Column(String(255), nullable=False)
    phone = db.Column(Integer, unique=True, nullable=False)
    program_id = db.Column(Integer, ForeignKey(Program.id), nullable=False)
    PrimaryKeyConstraint(user_id, id)

    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            yield {'id': row[0], 'name': row[1], 'address': row[2], 'phone': row[3], 'program_id': row[4]}


# NOTE: table name is Academic_Record
class AcademicRecord(db.Model, MyMixin):
    user_id = db.Column(Integer)
    student_id = db.Column(Integer, ForeignKey(Student.id), nullable=False)
    course_id = db.Column(Integer, ForeignKey(Course.id), nullable=False)
    # TODO: consider converting to enum (A, B, C, D, F)
    grade = db.Column(CHAR(1), nullable=False)
    year = db.Column(SmallInteger, nullable=False)
    # TODO: consider converting to enum (1, 2, 3, 4) for (Winter, Spring, Summer, Fall)
    term = db.Column(SmallInteger, nullable=False)
    PrimaryKeyConstraint(user_id, student_id, course_id, year, term)

    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            yield {'student_id': row[0], 'course_id': row[1], 'grade': row[2], 'year': row[3], 'term': row[4]}


class Listing(db.Model, MyMixin):
    user_id = db.Column(Integer)
    program_id = db.Column(Integer, ForeignKey(Program.id), nullable=False)
    course_id = db.Column(Integer, ForeignKey(Course.id), nullable=False)
    PrimaryKeyConstraint(user_id, program_id, course_id)

    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            yield {'program_id': row[0], 'course_id': row[1]}


class Request(db.Model, MyMixin):
    user_id = db.Column(Integer)
    student_id = db.Column(Integer, ForeignKey(Student.id), nullable=False)
    course_id = db.Column(Integer, ForeignKey(Course.id), nullable=False)
    PrimaryKeyConstraint(user_id, student_id, course_id)

    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            yield {'student_id': row[0], 'course_id': row[1]}