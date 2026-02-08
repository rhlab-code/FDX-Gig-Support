#

import json
import logging
import os
import requests
import sys

from websec import WebsecTokenService
from trim_mac import trim_mac

class BaccCos:
    BACC_SERVER = 'https://provisioning-baccws-service.xsp.comcast.net/'
    GET_URL = BACC_SERVER + 'api/provisioning/v1/provisioningbaccws/getDeviceDetailsWithoutLease'
    SET_URL = BACC_SERVER + 'api/provisioning/v1/provisioningbaccws/setCOS'
    WEBSEC_LABEL = 'bacc'

    KNOWN_RDUS = [
        'rdu07.g.crnrstn.comcast.net',

        'rdu01.g.comcast.net',
        'rdu02.g.comcast.net',
        'rdu03.g.comcast.net',
        'rdu04.g.comcast.net',
        'rdu05.g.comcast.net',
        'rdu06.g.comcast.net',
        'rdu07.g.comcast.net',
    ]

    def __init__(self, timeout=10):
        self.websec = WebsecTokenService()
        self.timeout = timeout

    def _make_req_data(self, rdu_fqdn, device_mac):
        mac_plain = trim_mac(device_mac, formats='plain')
        token = self.websec.get_token(self.WEBSEC_LABEL)
        req_headers = {
            'Accept': 'application/json',
            'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json',
        }
        req_data = {
            'accountNumber': '',
            'duid': '',
            'macAddress': mac_plain,
            'rduFqdn': rdu_fqdn,
        }
        return req_headers, req_data

    def get_device_cos(self, rdu_fqdn, device_mac):
        if rdu_fqdn:
            rdu_candidates = [rdu_fqdn]
        else:
            rdu_candidates = self.KNOWN_RDUS

        result = (None, None)
        for rdu in rdu_candidates:
            logging.info('Querying %s for %s', rdu, device_mac)
            req_headers, req_data = self._make_req_data(rdu, device_mac)
            try:
                resp = requests.post(self.GET_URL, headers=req_headers, json=req_data,
                                     timeout=self.timeout)
            except Exception as ex:
                logging.debug('%s getDeviceDetailsWithoutLease threw %s', rdu, ex)
                continue

            if resp.status_code != 200:
                logging.debug('%s status code: %d', rdu, resp.status_code)
                continue

            try:
                resp_json = resp.json()
                cos_val = resp_json['return']['cos']
            except:
                logging.debug("Unable to parse response: %s", resp.text)
                continue

            result = (rdu, cos_val)
            break

        return result

    def set_device_cos(self, rdu_fqdn, device_mac, cos_new):
        req_headers, req_data = self._make_req_data(rdu_fqdn, device_mac)
        req_data['cos'] = cos_new
        try:
            resp = requests.post(self.SET_URL, headers=req_headers, json=req_data,
                                 timeout=self.timeout)
        except Exception as ex:
            logging.warning('BACC setCOS threw %s', ex)
            return None

        if resp.status_code != 200:
            logging.warning('BACC status code: %d', resp.status_code)
            return None
        try:
            resp_json = resp.json()
            success = resp_json['success']
        except:
            logging.warning("Unable to parse response: %s", resp.text)
            return None

        return success

################

def main():
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--new-cos', type=str, help='New COS to set')
    parser.add_argument('--rdu', type=str, default=None, help='RDU FQDN')
    parser.add_argument(dest='mac', type=str, help='Device MAC address')

    args = parser.parse_args()

    ll = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=ll,
        format='%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(funcName)s|%(message)s')

    bc = BaccCos()
    logging.debug('new_cos=%s', args.new_cos)
    if args.new_cos:
        val = bc.set_device_cos(args.rdu, args.mac, args.new_cos)
    else:
        val = bc.get_device_cos(args.rdu, args.mac)

    print(val)

################

if __name__ == '__main__':
    main()
