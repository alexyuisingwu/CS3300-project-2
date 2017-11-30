from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.fields.html5 import EmailField
from wtforms.validators import InputRequired, Email, equal_to
from app.models import Account


class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[InputRequired()])
    email = EmailField('Email', validators=[Email()])
    password = PasswordField('Password', validators=[
        InputRequired(),
        equal_to('confirm_password', 'Passwords must match')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[InputRequired()])

    def validate(self):
        valid = True
        if not super().validate():
            valid = False
        if not self.username.errors:
            if Account.query.filter_by(username=self.username.data).first() is not None:
                self.username.errors.append('Username taken')
                valid = False
        if not self.email.errors:
            if Account.query.filter_by(email=self.email.data).first() is not None:
                self.email.errors.append('Email taken')
                valid = False
        return valid


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[InputRequired()])
    password = PasswordField('Password', validators=[InputRequired()])

    def validate(self):
        valid = True
        if not super().validate():
            valid = False
        if not self.username.errors:
            user = Account.query.filter_by(username=self.username.data).first()
            if user is None:
                self.username.errors.append('Username not found')
                return False
            if not self.password.errors and not user.validate_password(self.password.data):
                self.password.errors.append('Incorrect password')
                return False
        return valid
