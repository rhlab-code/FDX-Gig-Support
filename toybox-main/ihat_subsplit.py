#!/usr/bin/env python3

# Usage example:
#
#   #### Show the current modems on the subsplit exclusion list
#   $ python ihat_subsplit.py get
#
#   #### Add modems to the subsplit exclusion list
#   $ python ihat_subsplit.py to_subsplit 00:00:00:00:00:00 11:11:11:11:11:11
#
#   #### Remove modems from the subsplit exclusion list
#   $ python ihat_subsplit.py to_midsplit 00:00:00:00:00:00 11:11:11:11:11:11

import requests
import json
import sys

from websec import WebsecTokenService

################

IHAT_API_URL = 'https://api.ihat.comcast.com'

q_modify_subsplit_list = '''
mutation(
    $split_type: String!,
    $macs: [String]!
) {
  subSplitExclusionList(input: {
    modemMacAddresses: $macs
    splitType: $split_type
  }) {
    splitType
    message
    failedMacAddresses
    modemMacAddresses
  }
}
'''

q_get_subsplit_list = '''
query {
  subSplitExclusionFullList {
    count
    message
    modemMacAddresses
  }
}
'''

################

def _build_headers():
    ws = WebsecTokenService()
    token = ws.get_token('ihat')
    headers = {
        'Accept': 'application/json',
        'Contepnt-Type': 'application/json',
        'Authorization': 'Bearer ' + token,
    }
    return headers

def modify_subsplit_list(split_type, macs):
    headers = _build_headers()

    variables = {
        'split_type': split_type,
        'macs': macs,
    }
    data = {
        'query': q_modify_subsplit_list,
        'variables': variables,
    }

    resp = requests.post(IHAT_API_URL, headers=headers, json=data)
    if resp.status_code != 200:
        return None

    resp_data = resp.json().get('data', {})
    return resp_data

def get_subsplit_list():
    headers = _build_headers()
    data = {
        'query': q_get_subsplit_list,
    }

    resp = requests.post(IHAT_API_URL, headers=headers, json=data)
    if resp.status_code != 200:
        return None

    resp_data = resp.json().get('data', {})
    return resp_data

################

def main():
    cmd = sys.argv[1]

    if cmd == 'to_subsplit':
        macs = sys.argv[2:]
        result = modify_subsplit_list('LOW', macs)
    elif cmd == 'to_midsplit':
        macs = sys.argv[2:]
        result = modify_subsplit_list('MID', macs)
    elif cmd == 'get':
        result = get_subsplit_list()
    else:
        result = {
            'error': 'Unknown command: ' + cmd,
        }

    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
