from app import db, bcrypt
from sqlalchemy.types import *
from sqlalchemy import ForeignKey, UniqueConstraint, ForeignKeyConstraint, PrimaryKeyConstraint, text
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.declarative import declared_attr
from flask import session
import csv
from os import environ
from flask_login import UserMixin, current_user


# TODO: consider adding indices on (user_id, name) for tables like Instructor
# TODO: re-enable foreign key constraints and save unassigned (0) values as null instead
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
    def load_csv_helper(cls, csv_reader_generator, connection=None):
        rows = []
        for row in csv_reader_generator:
            user_id = current_user.id
            row['user_id'] = user_id
            rows.append(row)
        if connection is None:
            db.engine.execute(cls.__table__.insert(), rows, autocommit=True)
        else:
            if not environ.get('IS_HEROKU'):
                connection.execute('PRAGMA defer_foreign_keys=ON')
            connection.execute(cls.__table__.insert(), rows, autocommit=False)

    @classmethod
    def load_csv(cls, csv_filepath, connection=None):
        cls.load_csv_helper(cls.parse_csv(csv_filepath), connection)

    @classmethod
    def load_csv_by_file(cls, f, connection=None):
        cls.load_csv_helper(cls.parse_csv_by_file(f), connection)


# "user" is a reserved word in postgresql
class Account(db.Model, UserMixin):
    id = db.Column(Integer, primary_key=True, autoincrement=True)
    username = db.Column(String(255), nullable=False, unique=True)
    email = db.Column(String(255), nullable=False, unique=True)
    passhash = db.Column(db.String(128), nullable=False)
    current_term = db.Column(Integer, nullable=False, server_default=text("0"))

    @classmethod
    def get_hashed_password(cls, password):
        return bcrypt.generate_password_hash(password).decode('utf-8')

    def validate_password(self, password):
        return bcrypt.check_password_hash(self.passhash, password)


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
    course_id = db.Column(Integer, nullable=False)
    prereq_id = db.Column(Integer, nullable=False)
    ForeignKeyConstraint([user_id, course_id], [Course.user_id, Course.id], deferrable=True)
    ForeignKeyConstraint([user_id, prereq_id], [Course.user_id, Course.id], deferrable=True)

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
    course_id = db.Column(Integer, nullable=True)
    PrimaryKeyConstraint(user_id, id)
    ForeignKeyConstraint([user_id, course_id], [Course.user_id, Course.id], deferrable=True)

    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            # ignore initial instructor assignments
            yield {'id': row[0], 'name': row[1], 'office_hours': row[2], 'email': row[3], 'course_id': None}


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
    phone = db.Column(String(15), unique=True, nullable=False)
    program_id = db.Column(Integer, nullable=True)
    PrimaryKeyConstraint(user_id, id)
    ForeignKeyConstraint([user_id, program_id], [Program.user_id, Program.id], deferrable=True)

    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            temp_program_id = None if row[4] == '0' else row[4]
            yield {'id': row[0], 'name': row[1], 'address': row[2], 'phone': row[3], 'program_id': temp_program_id}


# NOTE: table name is Academic_Record
class AcademicRecord(db.Model, MyMixin):
    user_id = db.Column(Integer)
    student_id = db.Column(Integer, nullable=False)
    course_id = db.Column(Integer, nullable=False)
    # TODO: consider converting to enum (A, B, C, D, F)
    grade = db.Column(CHAR(1), nullable=False)
    year = db.Column(SmallInteger, nullable=False)
    # TODO: consider converting to enum (1, 2, 3, 4) for (Winter, Spring, Summer, Fall)
    term = db.Column(SmallInteger, nullable=False)
    PrimaryKeyConstraint(user_id, student_id, course_id, year, term)
    ForeignKeyConstraint([user_id, student_id], [Student.user_id, Student.id], deferrable=True)
    ForeignKeyConstraint([user_id, course_id], [Course.user_id, Course.id], deferrable=True)

    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            yield {'student_id': row[0], 'course_id': row[1], 'grade': row[2], 'year': row[3], 'term': row[4]}


class Listing(db.Model, MyMixin):
    user_id = db.Column(Integer)
    program_id = db.Column(Integer, nullable=False)
    course_id = db.Column(Integer, nullable=False)
    PrimaryKeyConstraint(user_id, program_id, course_id)
    ForeignKeyConstraint([user_id, program_id], [Program.user_id, Program.id], deferrable=True)

    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            yield {'program_id': row[0], 'course_id': row[1]}


class Request(db.Model, MyMixin):
    user_id = db.Column(Integer)
    student_id = db.Column(Integer, nullable=False)
    course_id = db.Column(Integer, nullable=False)
    PrimaryKeyConstraint(user_id, student_id, course_id)
    ForeignKeyConstraint([user_id, student_id], [Student.user_id, Student.id], deferrable=True)
    ForeignKeyConstraint([user_id, course_id], [Course.user_id, Course.id], deferrable=True)

    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            yield {'student_id': row[0], 'course_id': row[1]}
