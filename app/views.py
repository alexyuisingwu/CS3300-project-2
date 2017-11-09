from flask import url_for, redirect, render_template, request, json, abort
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import text
from app import app, db
from app.forms import RegistrationForm, LoginForm
from app.utils.database_utils import import_csv_by_file, import_csvs_by_filepath
from app.utils.utils import is_safe_url
from app.models import Account, Course, Instructor
from os import environ


# TODO: implement logout in UI
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
        if environ.get('IS_HEROKU'):
            connection.execute("SET CONSTRAINTS ALL DEFERRED")

        for file in files:
            import_csv_by_file(file, connection)

    return json.dumps({'success': True}), 200, {'ContentType': 'application/json'}


@app.route('/assign-instructors', methods=['GET', 'POST'])
@login_required
def assign_instructors():
    user_id = current_user.id
    if request.method == 'GET':
        courses = Course.query.filter_by(user_id=user_id)
        instructors = Instructor.query.filter_by(user_id=user_id)

        return render_template('assign-instructors.html', courses=courses, instructors=instructors)
    else:
        # TODO: error messages for no assignment
        for course_id, instructor_name in request.form.items():
            if course_id != 'csrf_token' and instructor_name != '':
                query = text(
                    'update instructor set course_id = :course_id where user_id = :user_id and name = :instructor_name')
                db.engine.execute(query.execution_options(autocommit=True), course_id=int(course_id), user_id=user_id,
                                  instructor_name=instructor_name)
        # NOTE: testing term increment
        current_user.increment_term()
        return redirect(url_for('assign_instructors_after_requests'))


@app.route('/assign-instructors-after-requests', methods=['GET', 'POST'])
@login_required
def assign_instructors_after_requests():
    user_id = current_user.id
    if request.method == 'GET':
        query = text("""select course.id, course.name, course.cost, count(*) as num_requests from
                        course left join request
                        on course.id = request.course_id
                        where course.user_id = :user_id
                        group by course.id""")
        courses = db.engine.execute(query.execution_options(autocommit=True), user_id=user_id).fetchall()
        instructors = Instructor.query.filter_by(user_id=user_id)

        return render_template('assign-instructors.html', courses=courses, instructors=instructors)
