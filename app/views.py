from flask import url_for, redirect, render_template, request, json, abort
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import text

from app import app, db
from app.forms import RegistrationForm, LoginForm
from app.models import Account, Course, Instructor
from app.utils.database_utils import import_csv_by_file, import_csvs_by_filepath
from app.utils.utils import is_safe_url


@app.route('/')
def index():
    if current_user.is_anonymous:
        return redirect(url_for('login'))
    else:
        return redirect(url_for('assign_instructors'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            username = request.form['username']
            email = request.form['email']
            passhash = Account.get_hashed_password(request.form['password'])
            query = text('insert into account (username, email, passhash) values (:username, :email, :passhash)')
            db.engine.execute(query.execution_options(autocommit=True), username=username, email=email,
                              passhash=passhash)

            user = Account.query.filter_by(username=username).first()
            login_user(user)
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


@app.route('/logout', methods=['GET'])
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
                query = text(
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
        query = text("""select t1.id, course.name as name, cost, num_requests, instructor.name as instructor from
                        (select course.id, count(request.user_id) as num_requests from
                                    course left join request
                                    on course.id = request.course_id
                                    and course.user_id = request.user_id
                                    and request.term = :term
                                    where course.user_id = :user_id
                                    group by course.id) as t1
                        inner join course
                        on course.user_id = :user_id
                        and t1.id = course.id
                        left join instructor
                        on instructor.user_id = :user_id
                        and course.id = instructor.course_id
                        order by t1.id;""")
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
                    query = text(
                        'update instructor set course_id = NULL where user_id = :user_id and course_id = :course_id')
                    connection.execute(query,
                                       course_id=int(course_id), user_id=user_id)
                    if instructor_name != '':
                        # update assignment
                        query = text(
                            'update instructor set course_id = :course_id where user_id = :user_id and name = :instructor_name')
                        connection.execute(query,
                                           course_id=int(course_id), user_id=user_id, instructor_name=instructor_name)
        return redirect(url_for('rejected_requests'))


# TODO: display granted requests
@app.route('/rejected-requests', methods=['GET', 'POST'])
@login_required
def rejected_requests():
    # TODO: prereq validation
    # TODO: consider index on temp table
    # TODO: move database modifications to POST request (either in calling function or after submit button pressed)
    if request.method == 'GET':
        with db.engine.begin() as connection:
            query = text("""CREATE temp TABLE course_helper AS 
                              SELECT course.id, 
                                     course.name, 
                                     instructor.id AS instructor_id 
                              FROM   course 
                                     left join instructor 
                                            ON course.user_id = instructor.user_id 
                                               AND course.id = instructor.course_id 
                              WHERE  course.user_id = :user_id; """)
            connection.execute(query, user_id=current_user.id)

            query = text("""CREATE temp TABLE request_missing_instructor AS 
                            SELECT request.course_id, 
                                   t1.course_name AS course_name,
                                   student.name AS student_name, 
                                   request.student_id 
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

            # selects all requests with missing prereqs
            # NOTE: a single course can appear multiple times as it can miss multiple prereqs
            query = text("""CREATE TEMP TABLE request_missing_prereq AS
                            SELECT request.student_id, 
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

            query = text("""SELECT request.course_id, 
                                   course.name  AS course_name, 
                                   request.student_id, 
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
                                                   WHERE  request.course_id = request_missing_instructor.course_id) 
                                   AND NOT EXISTS (SELECT 1 
                                                   FROM   request_missing_prereq 
                                                   WHERE  request.course_id = request_missing_prereq.course_id); 
            """)
            valid_requests = connection.execute(query,
                                                term=current_user.current_term, user_id=current_user.id).fetchall()

            reject_dict = {}

            for row in no_instructor_requests:
                reject_dict[(row.student_id, row.course_id)] = \
                    {'course_name': row.course_name, 'student_name': row.student_name, 'no_instructor': True}

            for row in missing_prereqs:
                key = (row.student_id, row.course_id)
                if key in reject_dict:
                    if 'missing_prereqs' in reject_dict[key]:
                        reject_dict[key]['missing_prereqs'].append({'id': row.prereq_id, 'name': row.prereq_name})
                    else:
                        reject_dict[key]['missing_prereqs'] = [{'id': row.prereq_id, 'name': row.prereq_name}]
                else:
                    reject_dict[key] = {
                        'missing_prereqs': [{'id': row.prereq_id, 'name': row.prereq_name}]
                    }

        return render_template('rejected-requests.html', reject_dict=reject_dict, valid_requests=valid_requests)
    else:
        current_user.increment_term()
        return redirect(url_for('assign_instructors'))
