#
# Retrieves the STB status using the deviceservice-stb-health service.
# See https://etwiki.sys.comcast.net/display/OSSTOOLS/deviceservice-stb-health+Service
#

from websec import WebsecTokenService
from trim_mac import trim_mac

import argparse
import io
import json
import random
import requests
import sys
import time

################

SERVICE_URL = 'https://deviceservices-stb-health-prod.codebig2.net/v1.0/api/checkStbHealth'
WS_LABEL = 'stb-health'

def query(stb_mac):
    '''Queries the STB's health data.
    '''
    ws = WebsecTokenService()
    token = ws.get_token(WS_LABEL)
    assert token

    mac = trim_mac(stb_mac)
    now = int(time.time())

    req_headers = {
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + token,
    }

    tracking_id = str(random.randint(0, 1000000000))

    req_data = {
        'mac': mac,
        'trackingId': tracking_id,
    }

    resp = requests.post(SERVICE_URL, headers=req_headers, json=req_data)
    if resp.status_code != 200:
        #sys.exit('Request failed: %d; %s' % (resp.status_code, resp.text))
        return None

    stb_health = resp.json()
    stb_health['timestamp'] = now

    return stb_health

################

def extract_tuners(stb_health):
    '''Extracts the video tuner information from the STB health data.
    '''

    tmp = stb_health and stb_health.get('component')
    tmp = tmp and tmp.get('attributes')
    tuners_raw = tmp and tmp.get('tuners')
    if not tuners_raw:
        return {}

    tuners = {} # freq => [pow, mer, ccw, ucw]
    for tuner in tuners_raw:
        f = tuner.get('frequency')
        if f is None or f == '0 Hz' or not f.endswith(' Hz'):
            continue

        freq = int(f[:-3])

        pow = float(tuner['power']['value'])
        mer = float(tuner['snr']['value'])
        ccw = int(tuner['corrected']['value'])
        ucw = int(tuner['uncorrectable']['value'])

        tuners[freq] = (pow, mer, ccw, ucw)

    return tuners

def query_tuners_repeatedly(stb_mac):
    prev_ts = None
    prev_tuners = None

    while True:
        stb_health = query(stb_mac)
        tuners = extract_tuners(stb_health)
        if not tuners:
            continue

        ts = stb_health.get('timestamp')
        time_delta = None if (ts is None or prev_ts is None) else ts - prev_ts
        r_tuners = []
        result = {
            'time_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(ts)),
            'time_unix': ts,
            'time_delta': time_delta,
            'tuners': r_tuners,
        }

        for freq in sorted(tuners.keys()):
            ccw_delta = None
            ucw_delta = None
            pow, mer, ccw, ucw = tuners[freq]
            if prev_tuners and freq in prev_tuners:
                ccw0, ucw0 = prev_tuners[freq][2:4]
                if ccw >= ccw0:
                    ccw_delta = ccw - ccw0
                if ucw >= ucw0:
                    ucw_delta = ucw - ucw0

            r_tuner = {
                'frequency': freq,
                'power': pow,
                'mer': mer,
                'ccw': ccw,
                'ucw': ucw,
                'ccw_delta': ccw_delta,
                'ucw_delta': ucw_delta,
            }
            r_tuner['ccw_delta_per_s'] = round(ccw_delta / time_delta, 1) \
                if time_delta and isinstance(ccw_delta, int) else None
            r_tuner['ucw_delta_per_s'] = round(ucw_delta / time_delta, 1) \
                if time_delta and isinstance(ucw_delta, int) else None
            r_tuners.append(r_tuner)

        yield(result)

        prev_ts = ts
        prev_tuners = tuners

def main():
    parser = argparse.ArgumentParser(
        description='Retrieves the STB status using the deviceservice-stb-health service'
    )
    parser.add_argument('--repeat', action='store_true',
                        help='Get video tuner status repeatedly')
    parser.add_argument('--duration', type=int, default=0,
                        help='Get video tuner status repeatedly for the duration')
    parser.add_argument('--out-file', type=str,
                        help='output file')
    parser.add_argument(dest='mac', type=str,
                        help='STB MAC address')
    args = parser.parse_args()

    ################

    if args.out_file:
        out_file = open(args.out_file, 'w')
    else:
        out_file = sys.stdout

    try:
        if args.repeat or args.duration > 0:
            t0 = time.time()
            for result in query_tuners_repeatedly(args.mac):
                if args.duration > 0 and time.time() - t0 > args.duration:
                    break
                json.dump(result, out_file)
                out_file.write('\n')
                out_file.flush()
        else:
            result = query(args.mac)
            json.dump(result, out_file, indent=2)
            out_file.write('\n')
    except KeyboardInterrupt:
        pass

    out_file.close()

if __name__ == '__main__':
    main()
