import pickle

import sqlalchemy
from flask import url_for, redirect, render_template, request, json, abort
from flask_login import login_user, logout_user, login_required, current_user
from sklearn.neural_network import MLPClassifier
from sqlalchemy import and_

from app import app, db
from app.forms import RegistrationForm, LoginForm
from app.models import Account, Course, Instructor, AcademicRecord, RequestPrediction, Student
from app.utils.database_utils import import_csv_by_file, import_csvs_by_filepath
from app.utils.utils import is_safe_url, get_random_grade, get_term_year


# TODO: consider converting to landing/home page with test data selection and/or user data upload
@app.route('/')
def index():
    if current_user.is_anonymous:
        return redirect(url_for('login'))
    else:
        return redirect(url_for('return_to_simulation'))


@app.route('/return-to-simulation')
@login_required
def return_to_simulation():
    if current_user.current_path == '/':
        return redirect(url_for('assign_instructors'))
    return redirect(current_user.current_path)


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

            query = sqlalchemy.text('insert into Request_Prediction (user_id) values (:user_id)')
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


# TODO: either delete or reintroduce csv upload option
# TODO: error messages for upload problems
@app.route('/csvs', methods=['GET', 'POST'])
@login_required
def upload_csvs():
    files = request.files.values()
    with db.engine.begin() as connection:
        for file in files:
            import_csv_by_file(file, connection)

    return json.dumps({'success': True}), 200, {'ContentType': 'application/json'}


@app.route('/assign-instructors', methods=['GET', 'POST'])
@login_required
def assign_instructors():
    user_id = current_user.id
    if request.method == 'GET':
        current_user.save_path(request.path)
        courses = Course.query.filter_by(user_id=user_id).order_by(Course.id)
        instructors = Instructor.query.filter_by(user_id=user_id).order_by(Instructor.name)

        # fetch predictive model for update
        request_prediction = RequestPrediction.query.filter_by(user_id=current_user.id).first()

        if request_prediction.model is not None:
            students = Student.query.filter_by(user_id=current_user.id).all()
            (overall_course_ids, expected_fraction_of_requests), (student_course_ids, probs) = \
                request_prediction.predict_students_requests(students, return_detailed_stats=True)

            return render_template('assign-instructors.html', courses=courses, instructors=instructors,
                                   overall_course_ids=overall_course_ids,
                                   expected_fraction_of_requests=expected_fraction_of_requests,
                                   student_course_ids=student_course_ids, student_probs=probs, students=students)

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
    # TODO: consider changing number of requests to number of valid requests (accounting for prereqs). Check if meets specifications first.
    if request.method == 'GET':
        current_user.save_path(request.path)
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
        current_user.save_path(request.path)
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
            missing_prereqs = connection.execute('select * from request_missing_prereq').fetchall()

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

        # TODO: consider querying database rather than passing data in forms or sessions
        # (students currently request courses they've already passed and also request courses they cannot take)
        return render_template('request-report.html', reject_dict=reject_dict, valid_requests=valid_requests,
                               no_instructor_requests=no_instructor_requests)
    else:
        with db.engine.begin() as connection:

            records = []
            current_year = get_term_year(current_user.current_term)

            # maps student_id to valid course request course_ids
            courses_requested = {}

            # hacky workaround for only modifying database (updating records and predictive model data) on POST request
            for student_id, course_id in request.form.items():
                if student_id != 'csrf_token':
                    student_id = int(student_id)
                    course_id = int(course_id)
                    # valid requests have positive ids, invalid requests have negative ids
                    if student_id > 0:
                        # insert records for all valid requests
                        record = {'user_id': current_user.id, 'student_id': student_id, 'course_id': course_id,
                                  'grade': get_random_grade(), 'year': current_year, 'term': current_user.current_term}
                        records.append(record)

                    if student_id in courses_requested:
                        courses_requested[abs(student_id)].append(abs(course_id))
                    else:
                        courses_requested[abs(student_id)] = [abs(course_id)]

            if records:
                connection.execute(AcademicRecord.__table__.insert(), records)

            # fetch predictive model for update
            data = RequestPrediction.query.filter_by(user_id=current_user.id).first()

            if data.model is None:
                attributes = Course.query \
                    .with_entities(Course.id) \
                    .filter_by(user_id=current_user.id).order_by(Course.id)

                attributes = [attribute[0] for attribute in attributes]

                from sklearn.preprocessing import MultiLabelBinarizer
                mlb = MultiLabelBinarizer(classes=attributes, sparse_output=True).fit(None)

                # TODO: consider filtering out suggestions for classes the student can't take due to prereqs
                # TODO: parameter tuning
                # identity activation as input is binary
                # very large regularization to punish overcomplex models
                # (true relationship is likely fairly simple direct prereq check)

                # TODO: consider encoding membership in course as -1, 1 instead for input
                # hidden layer should be between size of input and output layers
                model = MLPClassifier(solver='sgd', hidden_layer_sizes=(len(attributes), len(attributes)))

                query = sqlalchemy.text("""update Request_Prediction set model = :model, mlb = :mlb
                                                            where user_id = :user_id""")
                connection.execute(query, model=pickle.dumps(model), mlb=pickle.dumps(mlb), user_id=current_user.id)

            else:
                model = data.model
                mlb = data.mlb

            X = []
            y = []

            # creates input X = courses taken
            # creates output y = courses requested
            for student_id, course_ids in courses_requested.items():
                courses_taken = AcademicRecord.query \
                    .with_entities(AcademicRecord.course_id) \
                    .filter(and_(
                    AcademicRecord.user_id == current_user.id, AcademicRecord.student_id == student_id,
                    AcademicRecord.grade not in ('D', 'F')
                ))
                courses_taken = [course[0] for course in courses_taken]

                X.append(courses_taken)
                y.append(course_ids)

            X = mlb.transform(X)
            y = mlb.transform(y)

            if X.shape[0] > 0:
                try:
                    model.partial_fit(X, y)
                except ValueError:
                    model.fit(X, y)

                query = sqlalchemy.text("""update Request_Prediction set model = :model where user_id = :user_id""")
                connection.execute(query, model=pickle.dumps(model), user_id=current_user.id)

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

# TODO: consider refactoring raw SQL to sqlalchemy
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

            no_instructor_requests_count = connection.execute(
                'select count(*) from request_missing_instructor').scalar()

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
            missing_prereqs_count = connection.execute('select count(*) from request_missing_prereq').scalar()

            # selects all valid requests by subtracting all user requests from invalid requests
            valid_query = sqlalchemy.text("""SELECT COUNT(*)
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
                                                          request_missing_prereq.course_id); 
            """)
            valid_requests_count = connection.execute(valid_query,
                                                      term=current_user.current_term,
                                                      user_id=current_user.id).scalar()

            cost_query = sqlalchemy.text("""SELECT SUM(course.cost)
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
                                                          request_missing_prereq.course_id); 
                            """)

            cost = connection.execute(cost_query, term=current_user.current_term, user_id=current_user.id).scalar()

            total_requests_count = no_instructor_requests_count + missing_prereqs_count + valid_requests_count

            connection.execute('drop table if exists course_helper')
            connection.execute('drop table if exists request_missing_instructor')
            connection.execute('drop table if exists request_missing_prereq')

            labels = ["Valid Request", "Invalid Request"]
            values = [valid_requests_count, total_requests_count - valid_requests_count]

        return render_template('success-management.html', count=valid_requests_count, total=total_requests_count,
                               label=labels, values=values, cost=cost)
