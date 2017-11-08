from os import environ, urandom


class Config(object):
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BCRYPT_HANDLE_LONG_PASSWORDS = True


class ProductionConfig(Config):
    SECRET_KEY = environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = environ.get('DATABASE_URL')
    DEBUG = False
    TESTING = False


class DevelopmentConfig(Config):
    SECRET_KEY = urandom(24)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///local_database.db'
    DEBUG = True
    TESTING = True
