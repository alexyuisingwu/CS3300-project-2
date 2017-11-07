from flask import url_for, redirect, render_template, session, request, jsonify
from app import app
from app.database_utils import *


@app.route('/')
def index():
    clear_db()
    # import_csvs()
    session['term'] = 0

    return render_template('index.html')

# TODO: error messages for upload problems
# TODO: convert form to have upload categories for each filetype
@app.route('/csvs', methods=['POST'])
def upload_csvs():
    files = request.files.getlist("file")
    for file in files:
        import_csv(file)
        return render_template('index.html'), 201
