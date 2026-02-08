#

# genome_modem - Queries a modem status with Genome.
#
# Requires a WebSec credential labeled 'genome'

import io
import json
import logging
import requests
import sys

import math

from websec import WebsecTokenService
from trim_mac import trim_mac

################

WEBSEC_LABEL = 'genome'
GENOME_URL = 'https://nql.genome.comcast.com/'

def _build_genome_query(is_mac=False, sysprops=False, device_server=False, midsplit=False,
                        usqam=False, dsqam=False, dsqam_simple=False, ofdm=False, ofdma=False,
                        preeq_stats=False, preeq_coeffs=False):
    q_sysprops = '''
      system {
        sysName
        sysContact
        sysDescr
        sysUpTime
      }
    ''' if sysprops else ''

    q_device_server = '''
      deviceServer {
        configFile
        firmware
      }
    ''' if device_server else ''

    q_midsplit = 'midSplit' if midsplit else ''

    q_ofdma = '''
      ofdmaUpstream {
        ifIndex
        ifOperStatus

        ifHcOutOctets
        ifOutDiscards
        ifOutErrors

        statusOfdmaUsEntry {
          t3Timeouts
          t4Timeouts
          rangingAborteds
          t3Exceededs
          isMuted
          rangingStatus
        }
        ofdmaChanEntry {
          channelId
          subcarrierZeroFreq
          firstActiveSubcarrierNum
          lastActiveSubcarrierNum
          subcarrierSpacing
          txPower
          preEqEnabled
        }
        profileStats {
          iuc
          outOctets
        }
      }
    ''' if ofdma else ''

    q_usqam = '''
      cableUpstream {
        ifIndex
        channelId
        channelFrequency
        channelWidth
        ifOperStatus
        statusTxPower
        statusEqualization
      }
    ''' if usqam else ''

    if dsqam_simple:
        q_dsqam = '''
          cableDownstream {
            channelFrequency
            channelWidth
            channelPower
            signalQualityExtRxMer
            signalNoiseDecibel
          }
        '''
    elif dsqam:
        q_dsqam = '''
          cableDownstream {
            ifIndex
            channelFrequency
            channelWidth
            channelPower
            signalQualityExtRxMer
            signalNoiseDecibel
            unerroreds
            correcteds
            uncorrectables
          }
        '''
    else:
        q_dsqam = ''

    q_ofdm = '''
      ofdmDownstream {
        ifIndex
        ifOperStatus
        channelSubcarrierZeroFreq
        channelPlcFreq
        channelPower {
          centerFrequency
          rxPower
        }
        rxMerMeanDecibel
      }
    ''' if ofdm else ''

    q_intfc = 'interfaces {' + q_usqam + q_ofdma + q_dsqam + q_ofdm + '}' \
        if (q_usqam or q_ofdma or q_dsqam or q_ofdm) else ''

    q_preeq_stats = '''
        ofdmaPreEq {
          channelId
          coAdjStatus
          measStatus
          ampRipplePkToPk
          ampRippleRms
          ampMean
          ampSlope
          grpDelayRipplePkToPk
          grpDelayRippleRms
          grpDelayMean
          grpDelaySlope
        }
    ''' if preeq_stats else ''

    q_preeq_coeffs = '''
      ofdmaSet {
        result {
          channelId
          subCarrierZeroFreqHz
          subCarrierSpacingkHz
          firstActiveSubCarrierIndex
          preEqCoefficient {
            i
            q
          }
        }
      }
    ''' if preeq_coeffs else ''

    q_ofdm_rxmer = '''
      rxMerSet {
        result {
          channelId
          subCarrierZeroFreqHz
          firstActiveSubCarrierIndex
          subCarrierSpacingkHz
          samples
        }
      }
    ''' if ofdm else ''

    q_pnm = '''
      pnm {
    ''' + q_preeq_stats + q_preeq_coeffs + q_ofdm_rxmer + '''
      }
    ''' if (preeq_stats or preeq_coeffs or ofdm) else ''

    query_key = 'cableModemsByMacV3' if is_mac else 'cableModemsV3'
    addr_type = 'macs' if is_mac else 'ips'

    q = '''
    query($addrs: [String!]!) {
      %s (
        %s: $addrs
        version: V3
        timeout: 10000
      ) {
        timestamp
        mac
        ip
        %s
        %s
        %s
        %s
        %s
      }
    }''' % (query_key, addr_type, q_sysprops, q_device_server, q_midsplit, q_intfc, q_pnm)

    return query_key, q

################

def query_modem(addr, is_mac=True, out_file=None, **q_args):
    if is_mac:
        mac_plain, addr_q, _ = trim_mac(addr, 'all')
    else:
        addr_q = addr

    ws = WebsecTokenService()
    token = ws.get_token(WEBSEC_LABEL)
    headers = {
        'Accept': 'application/json',
        'Contepnt-Type': 'application/json',
        'Authorization': 'Bearer ' + token,
    }
    variables = {'addrs': [addr_q]}
    query_key, q = _build_genome_query(is_mac=is_mac, **q_args)
    data = {
        'query': q,
        'variables': variables,
    }
    resp = requests.post(GENOME_URL, headers=headers, json=data)
    if resp.status_code != 200:
        logging.warning('Genome TAP for %s failed: status_code=%r text=%s',
                        addr_q, resp.status_code, resp.text)
        return None

    tmp = resp.json().get('data', {})
    dev_info_all = tmp.get(query_key)
    if not dev_info_all or len(dev_info_all) != 1:
        logging.warning('Genome TAP for %s failed', addr_q)
        return None

    dev_info = dev_info_all[0]

    if is_mac:
        if dev_info.get('mac') != mac_plain:
            logging.warning('Genome TAP for %s failed %r', addr_q, dev_info)
            return None

    try:
        dev_info['mac'] = trim_mac(dev_info['mac'])
    except:
        pass

    if isinstance(out_file, io.TextIOBase):
        json.dump(dev_info, out_file, indent=2)
        out_file.write('\n')
    elif isinstance(out_file, str):
        with open(out_file, 'w') as f:
            json.dump(dev_info, f, indent=2)
            f.write('\n')
        logging.debug('%s -> %s', addr_q, out_file)

    return dev_info

################

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', dest='loglevel', action='store_const',
                        const=logging.DEBUG, default=logging.INFO)
    parser.add_argument('--dryrun', action='store_true')
    parser.add_argument('--out-file', type=str,
                        help='output file')
    parser.add_argument('--sysprops', action='store_true',
                        help='Add sysName, sysDescr, and sysUptime')
    parser.add_argument('--device-server', action='store_true',
                        help='Add firmware and configFile')
    parser.add_argument('--midsplit', action='store_true',
                        help='Add midsplit status')
    parser.add_argument('--ofdma', action='store_true',
                        help='Add OFDMA status')
    parser.add_argument('--dsqam', action='store_true',
                        help='Add DSQAM status')
    parser.add_argument('--dsqam-simple', action='store_true',
                        help='Add DSQAM simple status')
    parser.add_argument('--usqam', action='store_true',
                        help='Add USQAM status')
    parser.add_argument('--ofdm', action='store_true',
                        help='Add OFDM status')
    parser.add_argument('--preeq-stats', action='store_true',
                        help='Add OFDMA preequalizer statistics')
    parser.add_argument('--preeq-coeffs', action='store_true',
                        help='Add OFDMA preequalizer coefficients')
    parser.add_argument('--preeq-plot', action='store_true',
                        help='Plot OFDMA preequalizer coefficients')
    parser.add_argument('--ip', action='store_true',
                        help='IP instead of MAC')
    parser.add_argument(dest='addr', type=str,
                        help='Device MAC or IP address')
    args = parser.parse_args()

    if args.dryrun:
        k, q = _build_genome_query(
            is_mac=(not args.ip),
            sysprops=args.sysprops, device_server=args.device_server, midsplit=args.midsplit,
            usqam=args.usqam, dsqam=args.dsqam, dsqam_simple=args.dsqam_simple, ofdma=args.ofdma, ofdm=args.ofdm,
            preeq_stats=args.preeq_stats, preeq_coeffs=(args.preeq_coeffs or args.preeq_plot),
        )
        print(q)
        sys.exit(0)

    logging.basicConfig(
        level=args.loglevel,
        format='%(asctime)s %(levelname)s :%(lineno)d %(funcName)s|%(message)s')

    if args.ip:
        addr = args.addr
    else:
        addr = trim_mac(args.addr)

    xb_data = query_modem(
        addr, is_mac=(not args.ip), out_file=args.out_file,
        sysprops=args.sysprops, device_server=args.device_server, midsplit=args.midsplit,
        usqam=args.usqam, dsqam=args.dsqam, dsqam_simple=args.dsqam_simple, ofdma=args.ofdma, ofdm=args.ofdm,
        preeq_stats=args.preeq_stats, preeq_coeffs=(args.preeq_coeffs or args.preeq_plot)
    )
    if xb_data is None:
        sys.exit('Genome failed on ' + args.addr)

    if args.preeq_plot:
        import matplotlib.pyplot as plt

        has_plot = False
        tmp0 = xb_data.get('pnm')
        tmp1 = tmp0 and tmp0.get('ofdmaSet') or []
        for tmp2 in tmp1:
            tmp3 = tmp2 and tmp2.get('result')

            f_zero = tmp3 and tmp3.get('subCarrierZeroFreqHz')
            f_spc = tmp3 and tmp3.get('subCarrierSpacingkHz')
            f_idx = tmp3 and tmp3.get('firstActiveSubCarrierIndex')
            coeffs = tmp3 and tmp3.get('preEqCoefficient')

            if isinstance(f_zero, int) \
               and isinstance(f_spc, int) \
               and isinstance(f_idx, int) \
               and coeffs:
                f_lo = f_zero + 1000 * f_spc * f_idx
                freqs = [(f_lo + i * 1000 * f_spc) / 1e6 for i in range(len(coeffs))]
                amps = [20 * math.log10(math.hypot(x['i'], x['q'])) for x in coeffs]
                plt.plot(freqs, amps, lw=0.5)
                has_plot = True

        if has_plot:
            mac = xb_data.get('mac')
            ip = xb_data.get('ip')

            plt.title('OFDMA Preequalizer\n%s %s' % (mac, ip))
            plt.ylim([-15, 15])
            plt.grid(True)
            plt.show()

        if tmp0 and not args.preeq_coeffs:
            xb_data.pop('pnm')

    if not args.out_file:
        print(json.dumps(xb_data, indent=2))

if __name__ == '__main__':
    main()
