from math import ceil
from urllib.parse import urlparse, urljoin

from flask import request
from numpy import random

from app import app

start_year = 2017


def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and \
           ref_url.netloc == test_url.netloc


# NOTE: returns ndarray of selections with replacement if size is larger than 1
def get_random_grade(size=None):
    grades = ['A', 'B', 'C', 'D', 'F']
    weights = (0.35, 0.45, 0.1, 0.05, 0.05)

    return str(random.choice(grades, size=size, p=weights))


def get_term_name(term_num):
    season = get_term_season(term_num)
    year = get_term_year(term_num)
    return season + ' ' + str(year)


def get_term_year(term_num):
    year_offset = ceil(term_num / 4.)
    return start_year + year_offset


def get_term_season(term_num):
    terms = ('Fall', 'Winter', 'Spring', 'Summer')
    return terms[term_num % 4]


@app.context_processor
def utility_processor():
    return dict(get_term_name=get_term_name)
