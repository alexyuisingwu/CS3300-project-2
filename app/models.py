from app import db
from sqlalchemy.types import *
from sqlalchemy import ForeignKey, UniqueConstraint, PrimaryKeyConstraint
import csv


class MyMixin(object):
    @classmethod
    def parse_csv(cls, csv_filepath):
        pass

    @classmethod
    def load_csv(cls, csv_filepath):
        db.engine.execute(
            cls.__table__.insert(),
            [x for x in cls.parse_csv(csv_filepath)],
            autocommit=True)


class Course(db.Model, MyMixin):
    id = db.Column(Integer, primary_key=True)
    name = db.Column(String(255), unique=True, nullable=False)
    cost = db.Column(Integer, nullable=False)

    @classmethod
    def parse_csv(cls, csv_filepath):
        with open(csv_filepath) as f:
            reader = csv.reader(f, delimiter=',')
            for row in reader:
                yield {'id': row[0], 'name': row[1], 'cost': row[2]}


class Prereq(db.Model, MyMixin):
    course_id = db.Column(Integer, ForeignKey(Course.id), nullable=False)
    prereq_id = db.Column(Integer, ForeignKey(Course.id), nullable=False)
    PrimaryKeyConstraint(course_id, prereq_id)

    @classmethod
    def parse_csv(cls, csv_filepath):
        with open(csv_filepath) as f:
            reader = csv.reader(f, delimiter=',')
            for row in reader:
                yield {'course_id': row[0], 'prereq_id': row[1]}


class Instructor(db.Model, MyMixin):
    id = db.Column(Integer, primary_key=True)
    name = db.Column(String(255), nullable=False)
    office_hours = db.Column(String(255), nullable=False)
    email = db.Column(String(255), nullable=False)
    # NOTE: can't be unique as = 0 when instructor not teaching course
    course_id = db.Column(Integer, ForeignKey(Course.id), nullable=False)

    @classmethod
    def parse_csv(cls, csv_filepath):
        with open(csv_filepath) as f:
            reader = csv.reader(f, delimiter=',')
            for row in reader:
                yield {'id': row[0], 'name': row[1], 'office_hours': row[2], 'email': row[3], 'course_id': row[4]}


class Program(db.Model, MyMixin):
    id = db.Column(Integer, primary_key=True)
    name = db.Column(String(255), unique=True, nullable=False)

    @classmethod
    def parse_csv(cls, csv_filepath):
        with open(csv_filepath) as f:
            reader = csv.reader(f, delimiter=',')
            for row in reader:
                yield {'id': row[0], 'name': row[1]}


class Student(db.Model, MyMixin):
    id = db.Column(Integer, primary_key=True)
    name = db.Column(String(255), nullable=False)
    address = db.Column(String(255), nullable=False)
    phone = db.Column(Integer, unique=True, nullable=False)
    program_id = db.Column(Integer, ForeignKey(Program.id), nullable=False)

    @classmethod
    def parse_csv(cls, csv_filepath):
        with open(csv_filepath) as f:
            reader = csv.reader(f, delimiter=',')
            for row in reader:
                yield {'id': row[0], 'name': row[1], 'address': row[2], 'phone': row[3], 'program_id': row[4]}


class AcademicRecord(db.Model, MyMixin):
    student_id = db.Column(Integer, ForeignKey(Student.id), nullable=False)
    course_id = db.Column(Integer, ForeignKey(Course.id), nullable=False)
    # TODO: consider converting to enum (A, B, C, D, F)
    grade = db.Column(CHAR(1), nullable=False)
    year = db.Column(SmallInteger, nullable=False)
    # TODO: consider converting to enum (1, 2, 3, 4) for (Winter, Spring, Summer, Fall)
    term = db.Column(SmallInteger, nullable=False)
    PrimaryKeyConstraint(student_id, course_id, year, term)

    @classmethod
    def parse_csv(cls, csv_filepath):
        with open(csv_filepath) as f:
            reader = csv.reader(f, delimiter=',')
            for row in reader:
                yield {'student_id': row[0], 'course_id': row[1], 'grade': row[2], 'year': row[3], 'term': row[4]}


class Listing(db.Model, MyMixin):
    program_id = db.Column(Integer, ForeignKey(Program.id), nullable=False)
    course_id = db.Column(Integer, ForeignKey(Course.id), nullable=False)
    PrimaryKeyConstraint(program_id, course_id)

    @classmethod
    def parse_csv(cls, csv_filepath):
        with open(csv_filepath) as f:
            reader = csv.reader(f, delimiter=',')
            for row in reader:
                yield {'program_id': row[0], 'course_id': row[1]}


class Request(db.Model, MyMixin):
    student_id = db.Column(Integer, ForeignKey(Student.id), nullable=False)
    course_id = db.Column(Integer, ForeignKey(Course.id), nullable=False)
    PrimaryKeyConstraint(student_id, course_id)

    @classmethod
    def parse_csv(cls, csv_filepath):
        with open(csv_filepath) as f:
            reader = csv.reader(f, delimiter=',')
            for row in reader:
                yield {'student_id': row[0], 'course_id': row[1]}
