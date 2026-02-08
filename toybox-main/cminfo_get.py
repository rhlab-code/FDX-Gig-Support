#
# Retrieves CM info/status, related to LLD, from the CM's SNMP.
#
# Usage Examples
#
#   # 0. Prepare
#   # 0.1. Follow some of the instructions in README.md
#   # 0.1.1. (REQUIRED) Prepare the Python virtual environment
#   # 0.1.2. (OPTIONAL) Register SAT-ng client for Thanos, with websec.py
#   # 0.1.3. (OPTIONAL) Register SAT-ng client for the "genome:usmkeys:docsismanager" scope,
#        with websec.py, for headless retrieval of CM SNMP keys
#
#   # 0.2. (REQUIRED) Install Net-SNMP - http://www.net-snmp.org/download.html
#       For SNMP CLI, snmpbulkwalk in particular
#   # 0.2.1. Install SNMP MIB files to report the OIDs and object values symbolically
#       http://mibs.cablelabs.com/MIBs/DOCSIS/
#
#   # 0.3. (OPTIONAL) Install https://github.comcast.com/snmpv3/snmp-client/releases -
#       make it runnnable as "snmp_client" command
#       For retrieving CM SNMP keys using NTID-based authentication
#
#
#   # 1. Specify SNMPv2 community string.  Useful at CableLabs interop
#   (venv)% python cminfo_get,py cm1-cminfo.txt 10.32.225.171 --v2 public
#
#   # 2. Look up CM by IP address.  
#   #    Step 0.3 (snmp_client) is REQUIRED.
#   (venv)% python cminfo_get.py cm2-cminfo.txt 2001:0558:4070:0028:8C98:1234:5678:abcd  --ntid
#
#   # 3. Look up CM by MAC address in preprod environment.  
#   #    Step 0.1.2 (Thanos) is REQUIRED.
#   (venv)% python cminfo_get,py cm3-cminfo.txt 12:34:56:78:ab:cd  --ntid --thanos
#
#   # 4. Look up CM by MAC address in prod environment.
#   (venv)% python cminfo_get.py cm4-cminfo.txt 12:34:56:78:ab:cd  --ntid --thanos --prod
#
#   # 5. Look up CM by CPE IP address in preprod environment.
#   (venv)% python cminfo_get.py cm5-cminfo.txt 174.177.95.14  --ntid --cpe --thanos
#
#   # 6. Use headless retrieval of SNMPv3 keys.  
#   #    Step 0.1.3 (Genome USM key) is REQUIRED.
#   (venv)% python cminfo_get,py cm6-cminfo.txt 12:34:56:78:ab:cd  --thanos
#

import argparse
import ipaddress
import json
import logging
import os
import requests
import subprocess
import sys
import time

import trim_mac

################

OIDS = {
    ".1.3.6.1.2.1.1": "system",

    ".1.3.6.1.2.1.2.2": "ifTable",

    ".1.3.6.1.2.1.69.1.3": "docsDevSoftware",
    ".1.3.6.1.2.1.69.1.4": "docsDevServer",

    ".1.3.6.1.4.1.4491.2.1.21.1.2": "docsQosParamSetTable",
    ".1.3.6.1.4.1.4491.2.1.21.1.3": "docsQosServiceFlowTable",
    ".1.3.6.1.4.1.4491.2.1.21.1.4": "docsQosServiceFlowStatsTable",
    ".1.3.6.1.4.1.4491.2.1.21.1.26": "docsQosAggregateServiceFlowTable",
    ".1.3.6.1.4.1.4491.2.1.21.1.28": "docsQosAqpTable",
}


################

def _trim_addr(addr_raw):
    '''Trims an address string as a MAC or IP address.
    Trims a MAC address to the full 17-letter lowercase form.
    Trims an IPv6 address to the full 39-letter uppercase form.

    :param:addr_raw: an address string
    :return: (address_trimmed, address_type).  address_type is 'mac', 'ipv4', or 'ipv6'.
    '''

    addr_trim = None
    addr_type = None

    try:
        addr_trim = trim_mac.trim_mac(addr_raw)
        addr_type = 'mac'
    except:
        pass

    if addr_type is None:
        try:
            ip = ipaddress.ip_address(addr_raw)
        except:
            ip = None

        if isinstance(ip, ipaddress.IPv4Address):
            addr_trim = ip.exploded
            addr_type = 'ipv4'
        elif isinstance(ip, ipaddress.IPv6Address):
            addr_trim = ip.exploded.upper()
            addr_type = 'ipv6'

    return addr_trim, addr_type

################

def _thanos_lookup_cm(addr, prod_dev, retry=10):
    '''Looks up a CM by MAC or IP address

    param:addr: MAC or IP address of CM
    param:prod_dev: "prod" or "dev"

    return: MAC and IP address of CM
    '''

    import thanos
    assert prod_dev in ('prod', 'dev')

    k = 'K_CmRegStatus_RegStatus'
    addr_trim, addr_type = _trim_addr(addr)
    if addr_type == 'mac':
        filters = ['cmMacAddr=%s' % addr_trim]
    elif addr_type == 'ipv4':
        filters = ['ipV4Addr=%s' % addr_trim]
    elif addr_type == 'ipv6':
        filters = ['ipv6Addr=%s' % addr_trim]
    else:
        assert False

    cm_mac = None
    cm_ip = None
    for i in range(retry):
        if i > 0:
            logging.info('Will retry, take %d', i)
            time.sleep(10)
        try:
            r = thanos.thanos_query(k, filters, prod_dev=prod_dev)
            t1 = r and r.get('data')
            t2 = t1 and t1.get('result')
            t3 = t2 and len(t2) == 1 and t2[0]
            t4 = t3 and t3.get('metric')
        except:
            t4 = None
        if not isinstance(t4, dict):
            continue
        mac_ = t4.get('cmMacAddr')
        if not mac_:
            continue
        ip4_ = t4.get('ipV4Addr')
        if ip4_ and ip4_ != '0.0.0.0':
            cm_mac = mac_
            cm_ip = ip4_
            break
        ip6_ = t4.get('ipv6Addr')
        if ip6_ and ip6_ != '0000:0000:0000:0000:0000:0000:0000:0000':
            cm_mac = mac_
            cm_ip = ip6_
            break

    return cm_mac, cm_ip

def _thanos_lookup_cm_by_cpe(addr, prod_dev='dev', retry=10):
    assert prod_dev in ('prod', 'dev')

    import thanos

    addr_trim, addr_type = _trim_addr(addr)
    assert addr_type

    cm_mac = None
    cpe_mac = None
    cpe_ip = None

    k = 'K_CmCpeList'
    if addr_type == 'ipv4':
        filters = [
            'cpeIpv4Addr=%s' % addr_trim,
            'cpeType=CPE',
        ]
    elif addr_type == 'ipv6':
        filters = [
            'cpeIpv6Addr=%s' % addr_trim,
            'cpeType=CPE',
        ]
    else:
        filters = ['cpeMacAddr=%s' % addr_trim]

    for i in range(retry):
        if i > 0:
            logging.info('Will retry, take %d, %r, %s', i, filters, prod_dev)
            time.sleep(10)
        try:
            r = thanos.thanos_query(k, filters, prod_dev=prod_dev)
            t1 = r and r.get('data')
            t2 = t1 and t1.get('result')
            t3 = t2 and len(t2) == 1 and t2[0]
            t4 = t3 and t3.get('metric')
        except Exception as e:
            t4 = None

        cm_mac_ = None
        if isinstance(t4, dict):
            cm_mac_ = t4.get('cmMacAddr')
        if cm_mac_:
            cm_mac = cm_mac_
            cpe_mac = t4.get('cpeMacAddr')
            cpe_ip = t4.get('cpeIpv4Addr') or t4.get('cpeIpv6Addr')
            break

    return cm_mac, cpe_mac, cpe_ip

def _get_snmpv3_keys_genome(cm_ip, retry=10):
    '''Retrieves the SNMPv3 keys of a CM'''

    # NOTE: For preprod environment ONLY, as access to prod environment has been
    # unabailable to us.

    from websec import WebsecTokenService

    GENOME_KEY_SERVER = 'https://usm-keys-staging.genome.comcast.com/rt-keys'
    WEBSEC_LABEL = 'genome-snmp-dev'

    websec = WebsecTokenService()
    token = websec.get_token(WEBSEC_LABEL)

    hdrs = {
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/json',
    }
    d_json = {'devices': [cm_ip], 'retry': 2, 'timeout': 2}

    keys = (None, None, None)

    for i in range(retry):
        if i > 0:
            logging.info('Will retry, take %d', i)
            time.sleep(10)

        response = requests.post(GENOME_KEY_SERVER, json=d_json, headers=hdrs, timeout=10)
        key_info_all = response.json()
        logging.debug('key_info_all=%r', key_info_all)
        key_info = key_info_all.get(cm_ip)
        if key_info:
            sn = key_info.get('securityName')
            ak = key_info.get('authKey')
            pk = key_info.get('privKey')
            if sn and ak and pk:
                keys = (sn, ak, pk)
                break
            else:
                logging.warning('cm_ip=%s: Unable to obtain v3 keys (%r)', cm_ip, key_info)

    return keys

def _get_snmpv3_keys_ntidauth(cm_ip, retry=10):
    DEVNULL = subprocess.DEVNULL
    USER = 'docsisManager'
    cmd_snmp_key = [
        'snmp_client', '-v=3',  '-u=' + USER, '-output', 'json', '-snmpcall=key', cm_ip,
    ]

    ak = None
    pk = None
    for i in range(retry):
        if i > 0:
            logging.info('Will retry, take %d', i)
            time.sleep(10)

        ak_ = None
        pk_ = None
        try:
            logging.info('cmd=%r', cmd_snmp_key)
            p = subprocess.run(cmd_snmp_key, stdin=DEVNULL, capture_output=True)
            logging.info('rc=%d stdout=%r', p.returncode, p.stdout)
            j_raw = p.stdout.decode(errors='ignore')
            j = json.loads(j_raw)
            ak_ = j.get('authkey')
            pk_ = j.get('privkey')
            logging.info('ak=%s, pk=%s', ak_, pk_)
        except Exception as ex:
            logging.warning('Exception %s', ex)

        if ak_ and pk_:
            ak = ak_
            pk = pk_
            break

    if ak and pk:
        return USER, ak, pk
    else:
        return None, None, None

def query_cm_snmp(cm_ip, oids=OIDS, retry=10, prod_dev='dev', ntid_auth=False, v2str=None):
    DEVNULL = subprocess.DEVNULL

    cm_ip_trim, cm_ip_type = _trim_addr(cm_ip)

    logging.debug('cm_ip %s %s', cm_ip_trim, cm_ip_type)
    if cm_ip_type == 'ipv4':
        snmp_ip = cm_ip
    elif cm_ip_type == 'ipv6':
        snmp_ip = 'udp6:' + cm_ip
    else:
        assert False

    if v2str:
        cmd_snmp_walk = [
            'snmpbulkwalk', '-v2c', '-c', v2str, snmp_ip,
        ]
    else:
        if ntid_auth or prod_dev == 'prod':
            snmp_u, ak, pk = _get_snmpv3_keys_ntidauth(cm_ip_trim)
        else:
            snmp_u, ak, pk = _get_snmpv3_keys_genome(cm_ip_trim)

        cmd_snmp_walk = [
                'snmpbulkwalk', '-Ox', '-v3', '-a', 'MD5',
            '-l',  'authPriv', '-u', snmp_u, '-x', 'DES',
            '-3k', '0x' + ak, '-3K', '0x' + pk, snmp_ip,
        ]

    result = []
    for oid, oid_name in oids.items():
        cmd = cmd_snmp_walk + [oid]
        try:
            p = subprocess.run(cmd, stdin=DEVNULL, capture_output=True)
            logging.info('rc=%d cmd=%r', p.returncode, cmd)

            result.append('# %s %s\n%s\n' % (
                oid, oid_name, p.stdout.decode(errors='ignore')
            ))
        except Exception as ex:
            logging.warning('Exception %s', ex)

    return result

################

def main():
    #### 0. Parse the command line
    parser = argparse.ArgumentParser(
        description=(
            'Looks up a cable modem by MAC or IP address of itself or a CPE, '
            'and retrieves its SNMP tables'
        ),
        epilog=(
            'Requires snmpbulkwalk (Net-SNMP CLI).\n'
            'Requires SAT-ng genome:usmkeys:docsismanager scope for headless retrival of SNMP keys.\n'
            'Requires snmp_client (https://github.comcast.com/snmpv3/snmp-client/releases) for non-headless retrival of SNMP keys.\n'
            'Depends on thanos.py and websec.py.'
        ),
    )
    parser.add_argument('--debug', dest='loglevel', action='store_const',
                        const=logging.DEBUG, default=logging.INFO)
    parser.add_argument('--thanos', action='store_true', help='Uses Thanos to look up CM IP')
    parser.add_argument('--cpe', action='store_true', help='Looks up CM by CPE address')
    parser.add_argument('--prod', dest='prod_dev', action='store_const',
                        const='prod', default='dev')
    parser.add_argument('--v2', type=str, default=None, help='SNMPv2 community string')
    parser.add_argument('--ntid-auth', action='store_true',
                        help='Uses NTID authentication for retrieving SNMP keys')
    parser.add_argument(dest='out_file', type=str,
                        help='Output file')
    parser.add_argument(dest='addr', type=str,
                        help='MAC or IP address of CM or CPE')
    args = parser.parse_args()

    logging.basicConfig(
        level=args.loglevel,
        format='%(asctime)s %(levelname)s :%(lineno)d %(funcName)s|%(message)s')

    if os.path.exists(args.out_file):
        sys.exit('ERROR: %s exists' % args.out_file)

    #### 1. Look up CM MAC from CPE address if necessary
    cpe_mac = None
    cpe_ip = None
    if args.cpe:
        assert args.thanos
        cpe_addr, cpe_addr_type = _trim_addr(args.addr)
        assert cpe_addr_type in ('mac', 'ipv4', 'ipv6')
        if cpe_addr_type == 'mac':
            cpe_mac = cpe_addr
        else:
            cpe_ip = cpe_addr
        cm_addr, cpe_mac, cpe_ip = _thanos_lookup_cm_by_cpe(cpe_addr, args.prod_dev)
    else:
        cm_addr = args.addr

    #### 2. Look up CM MAC and IP address
    logging.info('cm_addr=%s', cm_addr)
    if args.thanos:
        cm_mac, cm_ip = _thanos_lookup_cm(cm_addr, args.prod_dev)
    else:
        cm_mac = None
        cm_ip, cm_addr_type = _trim_addr(cm_addr)
        assert cm_addr_type in ('ipv4', 'ipv6')

    logging.info('cm_mac=%s cm_ip=%s cpe_ip=%s', cm_mac, cm_ip, cpe_ip)
    if not cm_ip:
        sys.exit('ERROR: Unable to look up CM IP')

    #### 3. Query CM SNMP tables
    snmp_result = query_cm_snmp(cm_ip, prod_dev=args.prod_dev, ntid_auth=args.ntid_auth, v2str=args.v2)
    if not snmp_result:
        sys.exit('ERROR: Unable to query CM SNMP')

    #### 4. Generate the report fie
    date = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    with open(args.out_file, 'w') as f:
        f.write('date=%s\n' % date)
        f.write('cm_mac=%s\n' % cm_mac)
        f.write('cm_ip=%s\n' % cm_ip)
        f.write('cpe_mac=%s\n' % cpe_mac)
        f.write('cpe_ip=%s\n' % cpe_ip)
        f.write('\n')
        for e in snmp_result:
            f.write('%s\n' % e)

################

if __name__ == '__main__':
    main()
