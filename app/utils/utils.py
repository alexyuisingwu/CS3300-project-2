from math import ceil
from numpy import random
from urllib.parse import urlparse, urljoin

from flask import request

from app import app


def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and \
           ref_url.netloc == test_url.netloc


def get_random_grade():
    grades = ['A', 'B', 'C', 'D', 'F']
    weights = (0.35, 0.45, 0.1, 0.05, 0.05)

    return random.choice(grades, p=weights)


@app.context_processor
def utility_processor():
    def get_term_name(term_num):
        term_dict = {
            0: 'Fall',
            1: 'Winter',
            2: 'Spring',
            3: 'Summer'
        }
        term_num = int(term_num)
        year_offset = ceil(term_num / 4.)
        season_num = term_num % 4
        season = term_dict[season_num]
        year = 2017 + year_offset
        return season + ' ' + str(year)

    return dict(get_term_name=get_term_name)
