import pickle
import numpy as np
import os

import sqlalchemy
import weka.core.jvm as jvm
from flask import url_for, redirect, render_template, request, json, abort
from flask_login import login_user, logout_user, login_required, current_user
from weka.associations import Associator
from weka.core import serialization
from weka.core.dataset import Attribute, Instance, Instances

from app import app, db
from app.forms import RegistrationForm, LoginForm
from app.models import Account, Course, Instructor, AcademicRecord, WekaData
from app.utils.database_utils import import_csv_by_file, import_csvs_by_filepath
from app.utils.utils import is_safe_url, get_random_grade, get_term_year

EXCLUDED_PATHS_FOR_SAVING = {'/', '/logout', '/academic_records'}


# saves current page of user to restore progress after logout
@app.url_value_preprocessor
def save_path(endpoint, values):
    if not current_user.is_anonymous:
        path = request.path
        if path not in EXCLUDED_PATHS_FOR_SAVING:
            current_user.save_path(request.path)
    return None


@app.route('/')
def index():
    if current_user.is_anonymous:
        return redirect(url_for('login'))
    else:
        path = current_user.current_path
        if path == '/':
            return redirect(url_for('assign_instructors'))
        else:
            return redirect(path)


# TODO: refactor to use transaction
@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if request.method == 'POST':
        # TODO: enclose in transaction
        if form.validate_on_submit():
            username = request.form['username']
            email = request.form['email']
            passhash = Account.get_hashed_password(request.form['password'])
            query = sqlalchemy.text(
                'insert into account (username, email, passhash) values (:username, :email, :passhash)')
            db.engine.execute(query.execution_options(autocommit=True), username=username, email=email,
                              passhash=passhash)

            user = Account.query.filter_by(username=username).first()
            login_user(user)

            query = sqlalchemy.text('insert into Weka_Data (user_id) values (:user_id)')
            db.engine.execute(query.execution_options(autocommit=True), user_id=current_user.id)

            # TODO: consider adding option to choose test case in UI
            import_csvs_by_filepath()


            return redirect(url_for('index'))
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = request.form['username']
        user = Account.query.filter_by(username=username).first()
        login_user(user)
        next_page = request.args.get('next')
        if not is_safe_url(next_page):
            return abort(400)
        return redirect(next_page or url_for('index'))
    return render_template('login.html', form=form)


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


# TODO: error messages for upload problems
@app.route('/csvs', methods=['GET', 'POST'])
@login_required
def upload_csvs():
    files = request.files.values()
    with db.engine.begin() as connection:
        for file in files:
            import_csv_by_file(file, connection)

    return json.dumps({'success': True}), 200, {'ContentType': 'application/json'}


# TODO: consider error message if any instructors unassigned
@app.route('/assign-instructors', methods=['GET', 'POST'])
@login_required
def assign_instructors():
    user_id = current_user.id
    if request.method == 'GET':
        courses = Course.query.filter_by(user_id=user_id).order_by(Course.id)
        instructors = Instructor.query.filter_by(user_id=user_id).order_by(Instructor.name)

        return render_template('assign-instructors.html', courses=courses, instructors=instructors)
    else:
        for course_id, instructor_name in request.form.items():
            if course_id != 'csrf_token' and instructor_name != '':
                query = sqlalchemy.text(
                    'update instructor set course_id = :course_id where user_id = :user_id and name = :instructor_name')
                db.engine.execute(query.execution_options(autocommit=True), course_id=int(course_id), user_id=user_id,
                                  instructor_name=instructor_name)
        return redirect(url_for('assign_instructors_after_requests'))


@app.route('/assign-instructors-after-requests', methods=['GET', 'POST'])
@login_required
def assign_instructors_after_requests():
    user_id = current_user.id
    # TODO: consider changing number of requests to number of valid requests (accounting for prereqs)
    if request.method == 'GET':
        query = sqlalchemy.text("""SELECT t1.id, 
                               course.name, 
                               cost, 
                               num_requests, 
                               instructor.name AS instructor 
                        FROM   (SELECT course.id, 
                                       Count(request.user_id) AS num_requests 
                                FROM   course 
                                       LEFT JOIN request 
                                              ON course.id = request.course_id 
                                                 AND course.user_id = request.user_id 
                                                 AND request.term = :term 
                                WHERE  course.user_id = :user_id 
                                GROUP  BY course.id) AS t1 
                               INNER JOIN course 
                                       ON course.user_id = :user_id 
                                          AND t1.id = course.id 
                               LEFT JOIN instructor 
                                      ON instructor.user_id = :user_id 
                                         AND course.id = instructor.course_id 
                        ORDER  BY t1.id; """)
        courses = db.engine.execute(query.execution_options(autocommit=True), user_id=user_id,
                                    term=current_user.current_term).fetchall()
        instructors = Instructor.query.filter_by(user_id=user_id).order_by(Instructor.name)

        return render_template('assign-instructors-after-requests.html', courses=courses, instructors=instructors)
    if request.method == 'POST':
        # transaction used as update statements out of order can cause duplicate key error if instructors swapped
        with db.engine.begin() as connection:
            for course_id, instructor_name in request.form.items():
                if course_id != 'csrf_token':
                    # clear old instructor assignment
                    query = sqlalchemy.text(
                        'update instructor set course_id = NULL where user_id = :user_id and course_id = :course_id')
                    connection.execute(query,
                                       course_id=int(course_id), user_id=user_id)
                    if instructor_name != '':
                        # update assignment
                        query = sqlalchemy.text(
                            'update instructor set course_id = :course_id where user_id = :user_id and name = :instructor_name')
                        connection.execute(query,
                                           course_id=int(course_id), user_id=user_id, instructor_name=instructor_name)
        return redirect(url_for('request_report'))


# TODO: handle running out of request files
@app.route('/request-report', methods=['GET', 'POST'])
@login_required
def request_report():
    if request.method == 'GET':
        with db.engine.begin() as connection:
            connection.execute('drop table if exists course_helper')
            # tracks courses for current user. instructor_id is id of assigned instructor (NULL if course unassigned)
            query = sqlalchemy.text("""CREATE temp TABLE course_helper AS 
                              SELECT course.id, 
                                     course.name, 
                                     instructor.id AS instructor_id 
                              FROM   course 
                                     left join instructor 
                                            ON course.user_id = instructor.user_id 
                                               AND course.id = instructor.course_id 
                              WHERE  course.user_id = :user_id; """)
            connection.execute(query, user_id=current_user.id)

            connection.execute('drop table if exists request_missing_instructor')
            # tracks requests for courses missing instructors
            query = sqlalchemy.text("""CREATE temp TABLE request_missing_instructor AS 
                            SELECT request.course_id AS course_id, 
                                   t1.course_name AS course_name,
                                   student.name AS student_name, 
                                   request.student_id AS student_id
                            FROM   (SELECT id   AS course_id, 
                                           name AS course_name 
                                    FROM   course_helper 
                                    WHERE  instructor_id IS NULL) AS t1 
                                   INNER JOIN request 
                                           ON request.user_id = :user_id 
                                              AND t1.course_id = request.course_id 
                                              AND request.term = :term 
                                   INNER JOIN student 
                                           ON student.user_id = :user_id 
                                              AND student.id = request.student_id;""")
            connection.execute(query, user_id=current_user.id, term=current_user.current_term)

            no_instructor_requests = connection.execute('select * from request_missing_instructor').fetchall()

            connection.execute('drop table if exists request_missing_prereq')

            # tracks requests for courses with missing prereqs
            # NOTE: a single course can appear multiple times as its request can miss multiple prereqs
            query = sqlalchemy.text("""CREATE TEMP TABLE request_missing_prereq AS
                            SELECT request.student_id as student_id, 
                                   student.name AS student_name, 
                                   request.course_id, 
                                   course1.name AS course_name, 
                                   prereq.prereq_id, 
                                   course2.name AS prereq_name 
                            FROM   prereq 
                                   INNER JOIN request 
                                           ON request.user_id = prereq.user_id 
                                              AND request.term = :term 
                                              AND request.course_id = prereq.course_id 
                                              AND request.user_id = :user_id 
                                   INNER JOIN course AS course1 
                                           ON course1.user_id = :user_id 
                                              AND request.course_id = course1.id 
                                   INNER JOIN course AS course2 
                                           ON course2.user_id = :user_id 
                                              AND prereq.prereq_id = course2.id 
                                   INNER JOIN student 
                                           ON student.user_id = :user_id 
                                              AND request.student_id = student.id 
                            WHERE  NOT EXISTS (SELECT * 
                                               FROM   academic_record 
                                               WHERE  user_id = :user_id 
                                                      AND grade NOT IN ( 'D', 'F' ) 
                                                      AND course_id = prereq_id);""")
            connection.execute(query, user_id=current_user.id, term=current_user.current_term)
            missing_prereqs = connection.execute('select * from request_missing_prereq')

            # selects all valid requests by subtracting all user requests from invalid requests
            query = sqlalchemy.text("""SELECT request.course_id, 
                                   course.name  AS course_name, 
                                   request.student_id AS student_id, 
                                   student.name AS student_name 
                            FROM   request 
                                   INNER JOIN course 
                                           ON request.user_id = course.user_id 
                                              AND request.course_id = course.id 
                                   INNER JOIN student 
                                           ON request.user_id = student.user_id 
                                              AND request.student_id = student.id 
                            WHERE  request.user_id = :user_id 
                                   AND request.term = :term 
                                   AND NOT EXISTS (SELECT 1 
                                                   FROM   request_missing_instructor 
                                                   WHERE  request.course_id = 
                            request_missing_instructor.course_id) 
                                   AND NOT EXISTS (SELECT 1 
                                                   FROM   request_missing_prereq 
                                                   WHERE  request.course_id = 
                                                          request_missing_prereq.course_id) 
                            ORDER  BY request.student_id, 
                                      request.course_id; 
            """)
            valid_requests = connection.execute(query,
                                                term=current_user.current_term, user_id=current_user.id).fetchall()

            reject_dict = {}

            for row in no_instructor_requests:
                reject_dict[(row.student_id, row.course_id)] = \
                    {'course_name': row.course_name, 'student_name': row.student_name, 'no_instructor': True}

            for row in missing_prereqs:
                key = (row.student_id, row.course_id)
                # request already rejected as course has no instructor (so course_name and student_name already set)
                if key in reject_dict:
                    if 'missing_prereqs' in reject_dict[key]:
                        reject_dict[key]['missing_prereqs'].append({'id': row.prereq_id, 'name': row.prereq_name})
                    else:
                        reject_dict[key]['missing_prereqs'] = [{'id': row.prereq_id, 'name': row.prereq_name}]
                else:
                    reject_dict[key] = {
                        'missing_prereqs': [{'id': row.prereq_id, 'name': row.prereq_name}],
                        'course_name': row.course_name,
                        'student_name': row.student_name
                    }
            connection.execute('drop table if exists course_helper')
            connection.execute('drop table if exists request_missing_instructor')
            connection.execute('drop table if exists request_missing_prereq')

        return render_template('request-report.html', reject_dict=reject_dict, valid_requests=valid_requests)
    else:
        with db.engine.begin() as connection:

            records = []
            current_year = get_term_year(current_user.current_term)

            # maps student_id to valid course request course_ids
            courses_requested = {}

            # hacky workaround for only modifying database (updating records and weka data) on POST request
            for student_id, course_id in request.form.items():
                if student_id != 'csrf_token':
                    # insert records for all valid requests
                    record = {'user_id': current_user.id, 'student_id': student_id, 'course_id': course_id,
                              'grade': get_random_grade(), 'year': current_year, 'term': current_user.current_term}
                    records.append(record)

                    if student_id in courses_requested:
                        courses_requested[student_id].append(int(course_id))
                    else:
                        courses_requested[student_id] = [int(course_id)]

            if records:
                connection.execute(AcademicRecord.__table__.insert(), records)

            # fetch weka data for update
            data = WekaData.query\
                .with_entities(WekaData.data)\
                .filter_by(user_id=current_user.id).scalar()

            jvm.start(max_heap_size='512m')

            weka_data_filepath = os.path.join(os.path.dirname(__file__), 'tmp/{}'.format(current_user.id))

            if data is None:
                attributes = Course.query \
                    .with_entities(Course.id) \
                    .filter_by(user_id=current_user.id).order_by(Course.id).all()


                # maps course id to position of "Took" attribute in weka_attributes
                attribute_map = {}

                # stores weka attributes (columns)
                weka_attributes = []
                for i, attribute in enumerate(attributes):
                    attribute_map[attribute[0]] = len(weka_attributes)
                    weka_attributes.append(Attribute.create_nominal('Took course {}'.format(attribute[0]), labels=['y']))
                    weka_attributes.append(Attribute.create_nominal('Requested course {}'.format(attribute[0]), labels=['y']))

                instances = Instances.create_instances(
                    name="my_numpy_data",
                    atts=weka_attributes,
                    capacity=len(courses_requested.keys())
                )
            else:
                # TODO: convert to serialization as java objects can't be pickled
                with open(weka_data_filepath, 'wb+') as f:
                    f.write(data)
                    instances, associator = serialization.read_all(weka_data_filepath)
                    instances = Instances(jobject=instances)
                    associator = Associator(jobject=associator)

            # adds rows to weka input for each student
            for student_id, course_ids in sorted(courses_requested.items(), key=lambda item: item[0]):
                courses_taken = AcademicRecord.query \
                    .with_entities(AcademicRecord.course_id) \
                    .filter(
                            AcademicRecord.user_id == current_user.id and AcademicRecord.student_id == student_id
                            and AcademicRecord.grade != 'D' and AcademicRecord.grade != 'F'
                    ).all()

                # instance values for each student
                # NOTE: values are indices of label in nominal attributes
                # missing values are treated as not belonging to the item set for FPGrowth
                instance_values = np.full(instances.num_attributes, fill_value=Instance.missing_value())

                # adds courses taken by student to instance_values
                for i, row in enumerate(courses_taken):
                    course_id = row[0]
                    ind = attribute_map[course_id]
                    instance_values[ind] = 0

                # adds courses requested by student to instance_values
                for i, course_id in enumerate(course_ids):
                    ind = attribute_map[course_id] + 1
                    instance_values[ind] = 0

                inst = Instance.create_instance(instance_values)
                instances.add_instance(inst)


            print(instances)
            # TODO: fiddle with options

            associator = Associator(classname='weka.associations.FPGrowth', options=['-M', '0.00000001', '1', '-C', '0.00001', '-S'])
            associator.build_associations(instances)

            print(associator)


            # create empty file

            # TODO: modify to create if not exists
            with open(weka_data_filepath, 'wb+') as f:
                serialization.write_all(weka_data_filepath, [instances, associator])
                query = sqlalchemy.text('update Weka_Data set data = :data where user_id = :user_id')
                connection.execute(query, user_id=current_user.id, data=f.read())

            jvm.stop()

        current_user.increment_term()
        return redirect(url_for('assign_instructors'))


@app.route('/academic-records')
@login_required
def academic_records():
    query = sqlalchemy.text("""SELECT student.id   AS student_id, 
                           student.name AS student_name, 
                           course.id    AS course_id, 
                           course.name  AS course_name, 
                           year, 
                           term, 
                           grade 
                    FROM   academic_record 
                           INNER JOIN course 
                                   ON academic_record.user_id = course.user_id 
                                      AND academic_record.course_id = course.id 
                           INNER JOIN student 
                                   ON academic_record.user_id = student.user_id 
                                      AND academic_record.student_id = student.id 
                    WHERE  academic_record.user_id = :user_id 
                    ORDER  BY student_id, 
                              course_id, 
                              year, 
                              term """)

    records = db.engine.execute(query, user_id=current_user.id).fetchall()

    return render_template('academic-records.html', records=records)


@app.route('/restart-simulation', methods=['POST'])
@login_required
def restart_simulation():
    current_user.restart_simulation()
    return redirect(url_for('assign_instructors'))


# TODO: move queries into helper functions
@app.route('/success-management', methods=['GET', 'POST'])
@login_required
def success_management():
    if request.method == 'GET':
        with db.engine.begin() as connection:
            connection.execute('drop table if exists course_helper')
            # tracks courses for current user. instructor_id is id of assigned instructor (NULL if course unassigned)
            query = sqlalchemy.text("""CREATE temp TABLE course_helper AS 
                              SELECT course.id, 
                                     course.name, 
                                     instructor.id AS instructor_id 
                              FROM   course 
                                     left join instructor 
                                            ON course.user_id = instructor.user_id 
                                               AND course.id = instructor.course_id 
                              WHERE  course.user_id = :user_id; """)
            connection.execute(query, user_id=current_user.id)

            connection.execute('drop table if exists request_missing_instructor')
            # tracks requests for courses missing instructors
            query = sqlalchemy.text("""CREATE temp TABLE request_missing_instructor AS 
                            SELECT request.course_id AS course_id, 
                                   t1.course_name AS course_name,
                                   student.name AS student_name, 
                                   request.student_id as student_id 
                            FROM   (SELECT id   AS course_id, 
                                           name AS course_name 
                                    FROM   course_helper 
                                    WHERE  instructor_id IS NULL) AS t1 
                                   INNER JOIN request 
                                           ON request.user_id = :user_id 
                                              AND t1.course_id = request.course_id 
                                              AND request.term = :term 
                                   INNER JOIN student 
                                           ON student.user_id = :user_id 
                                              AND student.id = request.student_id;""")
            connection.execute(query, user_id=current_user.id, term=current_user.current_term)

            no_instructor_requests = connection.execute('select * from request_missing_instructor').fetchall()

            connection.execute('drop table if exists request_missing_prereq')

            # tracks requests for courses with missing prereqs
            # NOTE: a single course can appear multiple times as its request can miss multiple prereqs
            query = sqlalchemy.text("""CREATE TEMP TABLE request_missing_prereq AS
                            SELECT request.student_id as student_id, 
                                   student.name AS student_name, 
                                   request.course_id, 
                                   course1.name AS course_name, 
                                   prereq.prereq_id, 
                                   course2.name AS prereq_name 
                            FROM   prereq 
                                   INNER JOIN request 
                                           ON request.user_id = prereq.user_id 
                                              AND request.term = :term 
                                              AND request.course_id = prereq.course_id 
                                              AND request.user_id = :user_id 
                                   INNER JOIN course AS course1 
                                           ON course1.user_id = :user_id 
                                              AND request.course_id = course1.id 
                                   INNER JOIN course AS course2 
                                           ON course2.user_id = :user_id 
                                              AND prereq.prereq_id = course2.id 
                                   INNER JOIN student 
                                           ON student.user_id = :user_id 
                                              AND request.student_id = student.id 
                            WHERE  NOT EXISTS (SELECT * 
                                               FROM   academic_record 
                                               WHERE  user_id = :user_id 
                                                      AND grade NOT IN ( 'D', 'F' ) 
                                                      AND course_id = prereq_id);""")
            connection.execute(query, user_id=current_user.id, term=current_user.current_term)
            missing_prereqs = connection.execute('select * from request_missing_prereq')

            # selects all valid requests by subtracting all user requests from invalid requests
            valid_query = sqlalchemy.text("""SELECT COUNT(request.course_id)
                            FROM   request 
                                   INNER JOIN course 
                                           ON request.user_id = course.user_id 
                                              AND request.course_id = course.id 
                                   INNER JOIN student 
                                           ON request.user_id = student.user_id 
                                              AND request.student_id = student.id 
                            WHERE  request.user_id = :user_id 
                                   AND request.term = :term 
                                   AND NOT EXISTS (SELECT 1 
                                                   FROM   request_missing_instructor 
                                                   WHERE  request.course_id = 
                            request_missing_instructor.course_id) 
                                   AND NOT EXISTS (SELECT 1 
                                                   FROM   request_missing_prereq 
                                                   WHERE  request.course_id = 
                                                          request_missing_prereq.course_id) 
                            ORDER  BY request.student_id, 
                                      request.course_id; 
            """)
            valid_requests_count = connection.execute(valid_query,
                                                      term=current_user.current_term,
                                                      user_id=current_user.id).fetchall()

            cost_query = sqlalchemy.text("""SELECT SUM(course_cost) 
                                FROM (SELECT course.cost as course_cost
                            FROM   request 
                                   INNER JOIN course 
                                           ON request.user_id = course.user_id 
                                              AND request.course_id = course.id 
                                   INNER JOIN student 
                                           ON request.user_id = student.user_id 
                                              AND request.student_id = student.id 
                            WHERE  request.user_id = :user_id 
                                   AND request.term = :term 
                                   AND NOT EXISTS (SELECT 1 
                                                   FROM   request_missing_instructor 
                                                   WHERE  request.course_id = 
                            request_missing_instructor.course_id) 
                                   AND NOT EXISTS (SELECT 1 
                                                   FROM   request_missing_prereq 
                                                   WHERE  request.course_id = 
                                                          request_missing_prereq.course_id)); 
                            """)

            cost = connection.execute(cost_query, term=current_user.current_term, user_id=current_user.id).fetchall()

            total_query = sqlalchemy.text("""SELECT COUNT(request.course_id)
                            FROM   request 
                                   INNER JOIN course 
                                           ON request.user_id = course.user_id 
                                              AND request.course_id = course.id 
                                   INNER JOIN student 
                                           ON request.user_id = student.user_id 
                                              AND request.student_id = student.id 
                                    WHERE  request.user_id = :user_id 
                                   AND request.term = :term 
            """)
            total_requests_count = connection.execute(total_query, term=current_user.current_term,
                                                      user_id=current_user.id).fetchall();

            reject_dict = {}

            for row in no_instructor_requests:
                reject_dict[(row.student_id, row.course_id)] = \
                    {'course_name': row.course_name, 'student_name': row.student_name, 'no_instructor': True}

            for row in missing_prereqs:
                key = (row.student_id, row.course_id)
                # request already rejected as course has no instructor (so course_name and student_name already set)
                if key in reject_dict:
                    if 'missing_prereqs' in reject_dict[key]:
                        reject_dict[key]['missing_prereqs'].append({'id': row.prereq_id, 'name': row.prereq_name})
                    else:
                        reject_dict[key]['missing_prereqs'] = [{'id': row.prereq_id, 'name': row.prereq_name}]
                else:
                    reject_dict[key] = {
                        'missing_prereqs': [{'id': row.prereq_id, 'name': row.prereq_name}],
                        'course_name': row.course_name,
                        'student_name': row.student_name
                    }
            connection.execute('drop table if exists course_helper')
            connection.execute('drop table if exists request_missing_instructor')
            connection.execute('drop table if exists request_missing_prereq')

            labels = ["Valid Request", "Invalid Request"]
            values = [int(valid_requests_count[0][0]),
                      int(total_requests_count[0][0]) - int(valid_requests_count[0][0])]

    return render_template('success-management.html', count=valid_requests_count, total=total_requests_count,
                           label=labels, values=values, cost=cost)

# TODO: use apriori to predict student requests
# TODO: consider either: (pairing each request with all requests in previous term) OR
# TODO: (column for each course and whether it has been taken, output columns of each course and whether the student takes it)

# NOTE: problem with course approach is number of courses not known until file upload (runtime), and potentially different per user
