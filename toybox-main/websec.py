#

import http.client
import json
import logging
import os
import re
import sqlite3
import sys
import ssl
import time
import urllib.parse
import logging

################

class WebsecTokenService:
    def __init__(self, cache_file=None, timeout=10):
        if cache_file is None:
            cache_dir = os.path.dirname(os.path.realpath(__file__))
            cache_file = os.path.join(cache_dir, 'websec_cache.db')

        self.cache_file = cache_file
        self.timeout = timeout

        self._prepare_cache_db()

    def _prepare_cache_db(self):
        db = sqlite3.connect(self.cache_file)
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS  websec_token ('
                       + ' label STRING,'
                       + ' server_url STRING,'
                       + ' client_id STRING,'
                       + ' client_secret STRING,'
                       + ' token_scope STRING,'
                       + ' token STRING,'
                       + ' token_fetched_at INT,'
                       + ' token_expires_at INT'
                       + ')')

    def set_info(self, label, server_url, client_id, client_secret, token_scope=None):
        db = sqlite3.connect(self.cache_file)
        with db:
            db.execute('DELETE FROM  websec_token WHERE label = ?', [label])
            db.execute('INSERT INTO  websec_token'
                       + ' (label, server_url, client_id, client_secret,'
                       + ' token_scope, token, token_fetched_at, token_expires_at)'
                       + ' VALUES (?,?,?,?,?,?,?,?)',
                       [label, server_url, client_id, client_secret,
                        token_scope, '', 0, 0])

    def get_info(self, label):
        db = sqlite3.connect(self.cache_file)
        c = db.cursor()
        c.execute('SELECT'
                  + ' server_url, client_id, client_secret, token_scope,'
                  + ' token, token_expires_at FROM websec_token'
                  +' WHERE label = ?',
                  [label])
        row = c.fetchone()
        return row

    def get_labels(self):
        db = sqlite3.connect(self.cache_file)
        c = db.cursor()
        c.execute('SELECT label FROM websec_token ORDER BY label')
        labels = []
        for label, in c:
            labels.append(label)
        return labels

    def get_token(self, label, expiry_slack=60):
        row = self.get_info(label)
        if not row:
            logging.error('Unknown token label: %s', label)
            return None

        server_url, client_id, client_secret, token_scope, token, token_expires_at = row
        now = time.time()
        logging.debug('Found cached token expiring in %d seconds', token_expires_at - now)
        if now < token_expires_at - expiry_slack:
            return token

        ################

        token = None
        now = int(time.time())
        if token_scope == '':
            method = 'GET'
            headers = {
                'Accept': 'application/json',
                'X-Client-Id': client_id,
                'X-Client-Secret': client_secret,
            }
            payload = None
        else:
            method = 'POST'
            headers = {
                'Content-type': 'application/x-www-form-urlencoded',
            }
            payload = {
                'client_id': client_id,
                'client_secret': client_secret,
                'grant_type': 'client_credentials',
                'scope': token_scope,
            }

        m = re.match('https://([^/]+)(/.*)', server_url)
        assert m
        url_host, url_path = m.groups()
        logging.debug('url_host=%s', url_host)
        logging.debug('url_path=%s', url_path)

        params = None if payload is None \
            else urllib.parse.urlencode(payload)

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        conn = http.client.HTTPSConnection(url_host, context=ctx)
        logging.debug('headers=%r', headers)
        logging.debug('params=%r', params)
        conn.request(method, url_path, headers=headers, body=params)

        res = conn.getresponse()
        if res.status != 200:
            logging.error('Token server returned %d: %r', res.status, res.reason)
            return None

        token_info_raw = res.read().decode('utf-8', errors='ignore')
        token_info = json.loads(token_info_raw)

        token = token_info.get('access_token')
        token_type = token_info.get('token_type')
        expires_in = token_info.get('expires_in')

        if not isinstance(token, str):
            logging.error('Received invalid token: %r', token)
        elif not isinstance(expires_in, int):
            logging.error('Received invalid expires_in: %r', expires_in)
        elif token_type != 'Bearer':
            logging.error('Received invalid token_type: %r', token_type)
        else:
            logging.debug('Fetched token: %s', token)
            expires_at = now + expires_in
            try:
                db = sqlite3.connect(self.cache_file)
                with db:
                    db.execute('UPDATE websec_token SET'
                               + ' token = ?, token_fetched_at = ?, token_expires_at = ?'
                               + ' WHERE label = ?',
                               [token, now, expires_at, label])

            except Exception as ex:
                logging.warning('Unable to write to token cache: %s', ex)

        return token

################

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Retrieves and caches WebSec access tokens'
    )
    parser.add_argument('--debug', dest='loglevel', action='store_const',
                        const=logging.DEBUG, default=logging.INFO)

    parser.add_argument('--url', type=str, help='Websec server URL')
    parser.add_argument('--id', type=str, help='Client ID')
    parser.add_argument('--secret', type=str, help='Client secret')
    parser.add_argument('--scope', type=str, help='Websec scope')

    parser.add_argument('--cache-file', type=str, help='Cache file')
    parser.add_argument('--show', action='store_true', help='Show the account info')

    parser.add_argument('--bearer', action='store_true',
                        help='Shows the token in Authorization: Bearer format')

    parser.add_argument('label', type=str,
                        help='Nickname to the set of WebSec client ID and scopes')

    args = parser.parse_args()

    logging.basicConfig(
        level=args.loglevel,
        format='%(asctime)s %(levelname)s :%(lineno)d %(funcName)s|%(message)s'
    )

    ################

    ws = WebsecTokenService()
    if args.label == 'list':
        # List the registered labels
        labels = ws.get_labels()
        for label in labels:
            print(label)
    elif args.show:
        # Show the label's registered information
        info = ws.get_info(args.label)
        if info:
            print(args.label,
                  '--url', repr(info[0]),
                  '--id', repr(info[1]),
                  '--secret', repr(info[2]),
                  '--scope', repr(info[3])
                  )
        else:
            print(args.label, 'not found')
    elif args.url and args.id and args.secret:
        # Create/update the account info for the label
        ws.set_info(args.label, args.url, args.id, args.secret, args.scope)
    else:
        # Retrieve a valid websec token
        token = ws.get_token(args.label)
        if args.bearer:
            print('{"Authorization": "Bearer %s"}' % token)
        else:
            print(token)

if __name__ == '__main__':
    main()
