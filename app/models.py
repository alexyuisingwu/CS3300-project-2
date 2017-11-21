import csv

from flask_login import UserMixin, current_user
from sqlalchemy import UniqueConstraint, ForeignKeyConstraint, PrimaryKeyConstraint, text, Index
from sqlalchemy.types import *

from app import db, bcrypt


# TODO: find out if simulation allows for uploading csvs/data. Otherwise, some tables can have user_id removed (like course)
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

    def increment_term(self):
        with db.engine.begin() as connection:
            connection.execute('update account set current_term = current_term + 1 where id = {}'.format(self.id))
            connection.execute('update instructor set course_id = NULL')

    def restart_simulation(self):
        db.session.query(Account).filter_by(id=self.id).update({'current_term': 0})
        db.session.query(Instructor).filter_by(user_id=self.id).update({'course_id': None})
        db.session.query(AcademicRecord).filter_by(user_id=self.id).delete()
        db.session.commit()


class Course(db.Model, MyMixin):
    user_id = db.Column(Integer)
    id = db.Column(Integer)
    name = db.Column(String(255), nullable=False)
    cost = db.Column(Integer, nullable=False)
    PrimaryKeyConstraint(user_id, id)
    UniqueConstraint(user_id, name)
    ForeignKeyConstraint([user_id], [Account.id], ondelete='CASCADE')
    Index('course_user_id_name_idx', user_id, name, unique=True)

    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            yield {'id': row[0], 'name': row[1], 'cost': row[2]}

    def count_requests(self):
        return db.engine.execute("""select count(*) from
                                  course left join request
                                  on course.id = request.course_id
                                  where course.user_id = {}
                                  and course.id = {}
                                  group by course.id""".format(current_user.id, self.id)).scalar()

    @classmethod
    def count_requests_for_all_courses(cls):
        return db.engine.execute("""select course.id, count(*) as num_requests from
                                  course left join request
                                  on course.id = request.course_id
                                  where course.user_id = {}
                                  group by course.id""".format(current_user.id))


class Prereq(db.Model, MyMixin):
    user_id = db.Column(Integer)
    course_id = db.Column(Integer, nullable=False)
    prereq_id = db.Column(Integer, nullable=False)
    ForeignKeyConstraint([user_id, course_id], [Course.user_id, Course.id], deferrable=True, initially="DEFERRED",
                         ondelete='CASCADE')
    ForeignKeyConstraint([user_id, prereq_id], [Course.user_id, Course.id], deferrable=True, initially="DEFERRED",
                         ondelete='CASCADE')

    PrimaryKeyConstraint(user_id, course_id, prereq_id)
    ForeignKeyConstraint([user_id], [Account.id], ondelete='CASCADE')

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
    course_id = db.Column(Integer, nullable=True)

    PrimaryKeyConstraint(user_id, id)
    UniqueConstraint(user_id, course_id)
    ForeignKeyConstraint([user_id], [Account.id], ondelete='CASCADE')
    ForeignKeyConstraint([user_id, course_id], [Course.user_id, Course.id], deferrable=True, initially="DEFERRED",
                         ondelete='CASCADE')

    Index('instructor_user_id_name_idx', user_id, name)

    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            # ignore initial instructor assignments
            yield {'id': row[0], 'name': row[1], 'office_hours': row[2], 'email': row[3], 'course_id': None}


class Program(db.Model, MyMixin):
    user_id = db.Column(Integer)
    id = db.Column(Integer)
    name = db.Column(String(255), nullable=False)
    PrimaryKeyConstraint(user_id, id)
    UniqueConstraint(user_id, name)
    ForeignKeyConstraint([user_id], [Account.id], ondelete='CASCADE')

    Index('program_user_id_name_idx', user_id, name, unique=True)

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
    phone = db.Column(String(15), nullable=False)
    program_id = db.Column(Integer, nullable=True)
    PrimaryKeyConstraint(user_id, id)
    UniqueConstraint(user_id, phone)
    ForeignKeyConstraint([user_id], [Account.id], ondelete='CASCADE')
    ForeignKeyConstraint([user_id, program_id], [Program.user_id, Program.id], deferrable=True, initially="DEFERRED",
                         ondelete='CASCADE')
    Index('student_user_id_name_idx', user_id, name)

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
    ForeignKeyConstraint([user_id], [Account.id], ondelete='CASCADE')
    ForeignKeyConstraint([user_id, student_id], [Student.user_id, Student.id], deferrable=True, initially="DEFERRED",
                         ondelete='CASCADE')
    ForeignKeyConstraint([user_id, course_id], [Course.user_id, Course.id], deferrable=True, initially="DEFERRED",
                         ondelete='CASCADE')

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
    ForeignKeyConstraint([user_id], [Account.id], ondelete='CASCADE')
    ForeignKeyConstraint([user_id, program_id], [Program.user_id, Program.id], deferrable=True, initially="DEFERRED",
                         ondelete='CASCADE')

    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            yield {'program_id': row[0], 'course_id': row[1]}


class Request(db.Model, MyMixin):
    user_id = db.Column(Integer)
    student_id = db.Column(Integer, nullable=False)
    course_id = db.Column(Integer, nullable=False)
    term = db.Column(Integer, nullable=False)
    # each student in simulation can only request each course once per term
    PrimaryKeyConstraint(user_id, student_id, course_id, term)
    ForeignKeyConstraint([user_id], [Account.id], ondelete='CASCADE')
    ForeignKeyConstraint([user_id, student_id], [Student.user_id, Student.id], deferrable=True, initially="DEFERRED",
                         ondelete='CASCADE')
    ForeignKeyConstraint([user_id, course_id], [Course.user_id, Course.id], deferrable=True, initially="DEFERRED",
                         ondelete='CASCADE')
    Index('request_user_id_term_idx', user_id, term, unique=False)

    @classmethod
    def parse_csv_by_file(cls, f):
        reader = csv.reader(f, delimiter=',')
        for row in reader:
            yield {'student_id': row[0], 'course_id': row[1], 'term': f.name.split('/')[-1][8:-4]}

    @classmethod
    def get_current_requests(cls):
        return db.engine.execute('select * from request where user_id = {} and term = {}'
                                 .format(current_user.id, current_user.current_term)).fetchall()
