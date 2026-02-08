#

import requests
import json
import sys

from websec import WebsecTokenService

################################################################

IHAT_API_URL = 'https://api.ihat.comcast.com'

def build_headers():
    ws = WebsecTokenService()
    token = ws.get_token('ihat')
    headers = {
        'Accept': 'application/json',
        'Contepnt-Type': 'application/json',
        'Authorization': 'Bearer ' + token,
    }
    return headers

################

q_get = '''
query($mac: String) {
  tests(
    first: %d
    filter: { macAddress: { eq: $mac } }
  ) {
    edges {
      vertex {
        macAddress
        testDate
        error
        testCode
        message
        oudpError {
          code
          message
          details
        }
        setTopBoxResults {
          macAddress
          model
          qam1Power
          qam2Power
          dsRxPower
          usTxPower
          usOudpPower
          dBcDelta
          isolation %s
        }
      }
    }
    pageInfo {
      endCursor
      hasNextPage
    }
  }
}
'''

q_oudp = '''
          upstreamOfdmaOudp {
            frequency
            amplitude
          }
'''

def get_test_results(cmmac, oudp, first=10):
    headers = build_headers()
    q = q_get % (first, (q_oudp if oudp else ''))

    variables = {
        'mac': cmmac,
    }
    data = {
        'query': q,
        'variables': variables,
    }

    resp = requests.post(IHAT_API_URL, headers=headers, json=data)
    if resp.status_code != 200:
        sys.stderr.write('get_test_results: resp.status_code=%d resp.text=%r' % (resp.status_code, resp.text))
        return None

    resp_data = resp.json().get('data', {})
    return resp_data

################

q_run = '''
query($cm_mac: String!, $stb_macs: [String]!) {
    onDemandiHatTest(input: {
      modemMacAddress: $cm_mac,
      stbMacAddresses: $stb_macs,
    }) {
    modemMacAddress,
    stbMacAddresses,
    testCode
    message
  }
}'''

def run_test(cm_mac, stb_macs):
    headers = build_headers()
    variables = {
        'cm_mac': cm_mac,
        'stb_macs': stb_macs,
    }
    data = {
        'query': q_run,
        'variables': variables,
    }

    resp = requests.post(IHAT_API_URL, headers=headers, json=data)
    if resp.status_code != 200:
        sys.stderr.write('run_test: resp.status_code=%d resp.text=%r\n' % (resp.status_code, resp.text))
        return None

    resp_data = resp.json().get('data', {})
    return resp_data


################

def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(dest='cmd', type=str,
                        choices=['get', 'run'])
    parser.add_argument('--first', type=int, default=10)
    parser.add_argument('--oudp', action='store_true')
    parser.add_argument(dest='cm_mac', type=str,
                        help='CM MAC address')
    parser.add_argument(dest='stb_macs', type=str, nargs='*',
                        help='STB MAC addresses.  0 or more')
    args = parser.parse_args()

    if args.cmd == 'get':
        out = get_test_results(args.cm_mac, args.oudp, first=args.first)
    elif args.cmd == 'run':
        out = run_test(args.cm_mac, args.stb_macs)
    else:
        assert False

    print(json.dumps(out, indent=2))

if __name__ == '__main__':
    main()
