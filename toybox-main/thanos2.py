#
# Makes a Thanos query
#
# Usage Examples
#
#   #### Simple query of a metric (K_RpdInfo), for preprod/dev metrics
#   $ python thanos.py K_RpdInfo > simple.json
#
#   #### Query with a filter (by rpdName), for production metrics
#   $ python thanos.py --prod K_CmRegStatus_RegStatus rpdName=WKXIHN0011 > filtered.json
#
################################################################

import argparse
import json
import logging
import os
import re
import requests
import sys

from websec import WebsecTokenService

THANOS_SERVICE = dict(
    dev="https://api.preprod-metrics.ngan.comcast.net/api/v1",
    prod="https://api.metrics.ngan.comcast.net/api/v1",
)

################

def escape_percent(s):
    escaped = {
        '!': '%21',
        '"': '%22',
        '*': '%2a',
        '+': '%2b',
        '=': '%3d',
        '{': '%7b',
        '}': '%7d',
        '~': '%7e',
    }

    out = ''
    for c in s:
        out += escaped.get(c, c)

    return out
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def thanos_query(metric, filters=None, prod_dev='dev', duration=None, time_range=None):
    if filters is None:
        filters = []
    assert isinstance(filters, list)

    url_service = THANOS_SERVICE[prod_dev]

    ws_label = 'thanos-' + prod_dev
    ws = WebsecTokenService()
    token = ws.get_token(ws_label)
    assert token

    if metric in ('/labels', '/targets', '/rules'):
        url = url_service + metric
    elif metric.startswith('/label/'):
        url = url_service + metric
    else:
        if time_range \
           and re.match(r'(start=.*).*(end=.*).*(step=.*)?)', time_range):
            q = '/query_range?query=%s' % metric
            url_timerange = time_range
        else:
            q = '/query?query=%s' % metric
            logging.debug(q)
            if duration and re.match(r'((\d+)(ms|s|m|h|d|w|y))+$', duration):
                url_timerange = '[' + duration + ']'
            else:
                url_timerange = ''

        url_filters = []
        logging.debug('filters=%r', filters)
        for f in filters:
            m = re.match(r'(\w+)(=~?|![=~])(.*)', f)
            logging.debug('match=%s', m)
            if m:
                key = m.group(1)
                opr = escape_percent(m.group(2))
                val = escape_percent(m.group(3))
                logging.debug('key=%s opr=%s', key, opr)
                p = f'{key}{opr}%22{val}%22'
                url_filters.append(p)
        if url_filters:
            q += '%7b' + ','.join(url_filters) + '%7d'

        url = url_service + q + url_timerange
        logging.debug('url=%s', url)

    ################

    req_headers = {
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + token,
    }

    resp = requests.get(url, headers=req_headers)
    logging.debug('resp.status_code=%d', resp.status_code)
    if resp.status_code != 200:
        raise Exception('status code %d' % resp.status_code)
    else:
        return resp.json()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', dest='loglevel', action='store_const',
                        const=logging.INFO, default=logging.INFO)

    parser.add_argument('--prod', dest='prod_dev', action='store_const',
                        const='prod', default='dev')
    parser.add_argument('--dev', dest='prod_dev', action='store_const',
                        const='dev', default='dev')

    parser.add_argument('--indent', action='store_const',
                        const=2, default=None)

    parser.add_argument('--duration', type=str, default=None)
    parser.add_argument('--time-range', type=str, default=None)

    parser.add_argument(dest='metric', type=str)
    parser.add_argument(dest='filters', type=str, nargs='*')

    args = parser.parse_args()
    logging.info(f"Arguments: {args.metric}")

    ################

    result = thanos_query(args.metric, args.filters, prod_dev=args.prod_dev,
                          duration=args.duration, time_range=args.time_range)
    print(json.dumps(result, indent=args.indent))

################

if __name__ == '__main__':
    main()
