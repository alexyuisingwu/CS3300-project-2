from flask import url_for, redirect, render_template, session, request, jsonify, abort, json
from app import app
from app.database_utils import *
from app.forms import *
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text


# TODO: implement accounts+login

@app.route('/')
def index():
    clear_db()
    # import_csvs()
    session['term'] = 0

    return render_template('index.html')


# TODO: error messages for upload problems
@app.route('/csvs', methods=['GET', 'POST'])
def upload_csvs():
    files = request.files.values()
    with db.engine.begin() as connection:
        if environ.get('IS_HEROKU'):
            connection.execute("SET CONSTRAINTS ALL DEFERRED")

        for file in files:
            import_csv(file, connection)

    return json.dumps({'success': True}), 200, {'ContentType': 'application/json'}


@app.route('/assign-instructors', methods=['GET', 'POST'])
def assign_instructors():
    # TODO: change when users implemented
    user_id = session.get('user_id', 1)
    if request.method == 'GET':
        query = text('select * from course where user_id = :user_id')
        courses = db.engine.execute(query.execution_options(autocommit=True), user_id=user_id).fetchall()
        query = text('select * from instructor where user_id = :user_id')
        instructors = db.engine.execute(query.execution_options(autocommit=True), user_id=user_id).fetchall()

        return render_template('assign-instructors.html', courses=courses, instructors=instructors)
    else:
        # TODO: error messages for no assignment
        for course_id, instructor_name in request.form.items():
            if course_id != 'csrf_token' and instructor_name != '':
                query = text(
                    'update instructor set course_id = :course_id where user_id = :user_id and name = :instructor_name')
                db.engine.execute(query.execution_options(autocommit=True), course_id=int(course_id), user_id=user_id,
                                  instructor_name=instructor_name)
        pass
