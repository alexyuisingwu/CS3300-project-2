from flask import url_for, redirect, render_template, session, request, jsonify, abort
from app import app
from app.database_utils import *
from app.forms import *
from sqlalchemy.exc import IntegrityError


@app.route('/', methods=['GET', 'POST'])
def index():
    clear_db()
    # import_csvs()
    session['term'] = 0

    return render_template('index.html')


# TODO: error messages for upload problems
# TODO: convert form to have upload categories for each filetype
@app.route('/csvs', methods=['POST'])
def upload_csvs():
    files = request.files.values()
    with db.engine.begin() as connection:
        for file in files:
            import_csv(file, connection)
        return render_template('index.html'), 201


@app.route('/courses', methods=['POST'])
def upload_courses():
    return upload_csvs()
