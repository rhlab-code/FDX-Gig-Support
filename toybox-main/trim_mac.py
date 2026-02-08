#

import argparse
import json
import re
import sys

################

H2 = r'[0-9A-Fa-f]{1,2}'
H4 = r'[0-9A-Fa-f]{4}'

RE_PLAIN = r'[0-9A-Fa-f]{12}$'
RE_CISCO = f'({H4})\.({H4})\.({H4})$'
RE_COLON = f'({H2}):({H2}):({H2}):({H2}):({H2}):({H2})$'

def trim_mac(mac, formats='colon'):
    mac_plain = None

    # No separator (xxxxxxxxxxxx)
    m = re.match(RE_PLAIN, mac)
    if m:
        mac_plain = mac.lower()

    # Cisco Dots (xxxx.xxxx.xxxx)
    if mac_plain is None:
        m = re.match(RE_CISCO, mac)
        if m:
            mac_plain = (m.group(1) + m.group(2) + m.group(3)).lower()

    # Colons (xx:xx:xx:xx:xx:xx or x:xx:xx:x:xx:xx, etc)
    if mac_plain is None:
        m = re.match(RE_COLON, mac)
        if m:
            octets = [('0' + m.group(i))[-2:].lower() for i in range(1, 7)]
            mac_plain = ''.join(octets)

    if mac_plain is None:
        raise ValueError('Malformed MAC address: "%s"' % mac)

    mac_colon = ':'.join(mac_plain[i:i+2] for i in range(0, 12, 2))
    mac_cisco = '.'.join(mac_plain[i:i+4] for i in range(0, 12, 4))

    if formats == 'colon':
        return mac_colon
    elif formats == 'cisco':
        return mac_cisco
    elif formats == 'plain':
        return mac_plain
    else:
        return mac_plain, mac_colon, mac_cisco

################

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plain', action='store_true',
                        help='Plain output (no colon delimiters)')
    parser.add_argument('--cisco', action='store_true',
                        help='Cisco output (dot delimiters)')
    parser.add_argument('--file', type=argparse.FileType('r'),
                        help='Read MAC addresses from file')
    parser.add_argument('--out', type=argparse.FileType('w'), default=sys.stdout)
    parser.add_argument(dest='mac', nargs='*', help='MAC address')
    args = parser.parse_args()

    macs = args.mac
    if args.file:
        for mac in args.file:
            macs.append(mac.strip())

    for mac in macs:
        try:
            mac_plain, mac_colon, mac_cisco = trim_mac(mac, formats='all')
        except Exception as ex:
            sys.exit('ERROR: %s' % ex)

        mac_out = mac_plain if args.plain else mac_cisco if args.cisco else mac_colon
        args.out.write('%s\n' % mac_out)

if __name__ == '__main__':
    main()
