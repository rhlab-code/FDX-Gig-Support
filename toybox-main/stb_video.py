#
# Retrieves the STB info using the deviceservice-video service.
# See https://etwiki.sys.comcast.net/display/OSSTOOLS/deviceservices-video
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

SERVICE_URL = 'https://deviceservices-video-prod.codebig2.net/v1.0/api/getSTBInfo'
WS_LABEL = 'stb-video'

def query(stb_mac, details=False):
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

        'cableCardInfo': details,
        'initInfo': details,
        'xreConnectionInfo': details,
        'stbAdditionalInfo': details,
        'xreBasicInfo': details,
        'ocapAdditionalInfo': details,
        'voiceRemoteBatteryInfo': details,
        'xreAdditionalInfo': details,
        'stbVisibilityInfo': details,
        'xconfInfo': details,
        'dsgInfo': details,
        'includeDSGTunnelInfo': details,
        'xreTotalInfo': details,

        'stbTunerInfo': True,
    }

    resp = requests.post(SERVICE_URL, headers=req_headers, json=req_data)
    if resp.status_code != 200:
        sys.stderr.write('ERROR: request failed: %d; %s\n' % (resp.status_code, resp.text))
        return None

    stb_info = resp.json()
    stb_info['timestamp'] = now

    return stb_info

def main():
    parser = argparse.ArgumentParser(
        description='Retrieves the STB video status using the deviceservice-video service'
    )
    parser.add_argument('--details', action='store_true', help='Retrives more details')
    parser.add_argument('--out-file', type=str, help='output file')
    parser.add_argument(dest='mac', type=str, help='STB MAC address')
    args = parser.parse_args()

    ################

    if args.out_file:
        out_file = open(args.out_file, 'w')
    else:
        out_file = sys.stdout

    result = query(args.mac, details=args.details)
    json.dump(result, out_file, indent=2)
    out_file.write('\n')

if __name__ == '__main__':
    main()
