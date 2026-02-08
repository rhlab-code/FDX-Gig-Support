# Unified Configuration Manager for EC FDX Amp Analyzer
# Version: 1.0
#
# Description:
# This file consolidates all device-specific configurations into a single,
# easy-to-manage dictionary. The main script will load the appropriate
# configuration from this file based on the --image command-line argument.
# ec_pnm_stats [statsType] [subBandId] [filename] - Collect EC stats
# statsType - EC PNM statistics type:
#     1 - EC Coefficient in freq. domain
#     2 - EC Coefficient in time domain
#     3 - EC Cancellation Depth
#     5 - Echo PSD
#     6 - Residual Echo PSD
#     7 - Downstream PSD
#     8 - Upstream PSD
# subBandId - sub-band id (0=default, 1, 2)
# filename  - path and filename to write to
#     /tmp/ec_pnm_stats_output_XX.dat (default)


CONFIGURATIONS = {
    'CS': {
        # CommScope Configuration
        'jumpbox_hostname': 'jump.autobahn.comcast.com',
        'jumpbox_username': "svcAutobahn",
        'target_ecm_mac': '24:a1:86:09:26:bc',
        'target_hostname': '',
        'target_username': "cli",
        'target_password': "cli",
        'path': "./output",
        'run_single': True,
        'result_filename_appendix': "_test",
        'get_ip_path': ".",
        'get_ip_script': 'Get_IP_v2.2.py',
        'cm_domain': 'PROD',
        'statType': [1, 3, 5, 6, 7, 8],
        'subBandId': [0, 1, 2],
        'rfboard_commands': ["showModuleInfo"],
        'hal_commands': ["/leap/lafe_show_status 0", "/leap/lafe_show_status 4", "/leap/lafe_show_status 5", "/leap/fafe_show_status 0", "/leap/fafe_show_status 4"]
    },
    'CCs': {
        # Comcast (RDK) Configuration
        'jumpbox_hostname': 'jump.autobahn.comcast.com',
        'jumpbox_username': "svcAutobahn",
        'target_ecm_mac': '',
        'target_hostname': '10.38.254.44',
        'target_username': "admin",
        'target_password': "AMPadmin",
        'path': "./output",
        'run_single': False,
        'result_filename_appendix': "_test",
        'get_ip_path': ".",
        'get_ip_script': 'Get_IP_v2.2.py',
        'cm_domain': 'PROD',
        'statType': [3, 6, 8],
        'subBandId': [0, 1, 2],
        'rfboard_commands': [],
        'hal_commands': []
    },
    'CC': {
        # Comcast (RDK) Configuration
        'jumpbox_hostname': 'jump.autobahn.comcast.com',
        'jumpbox_username': "svcAutobahn",
        'target_ecm_mac': '24:a1:86:0e:73:8c',
        'target_hostname': '',
        'target_username': "admin",
        'target_password': "AMPadmin",
        'path': "./output",
        'run_single': True,
        'result_filename_appendix': "_test",
        'get_ip_path': ".",
        'get_ip_script': 'Get_IP_v2.2.py',
        'cm_domain': 'PROD',
        'statType': [1, 5, 6, 7, 8],
        'subBandId': [0, 1, 2],
        'rfboard_commands': ["showModuleInfo"],
        'hal_commands': ["/leap/lafe_show_status 0", "/leap/lafe_show_status 4", "/leap/lafe_show_status 5", "/leap/fafe_show_status 0", "/leap/fafe_show_status 4"]
    },
    'SC': {
        # Sercomm Configuration
        'jumpbox_hostname': 'jump.autobahn.comcast.com',
        'jumpbox_username': "svcAutobahn",
        'target_ecm_mac': 'c4:0f:a6:fc:49:03',
        'target_hostname': '',
        'target_username': "root",
        'target_password': "",
        'path': "./output",
        'run_single': True,
        'result_filename_appendix': "_sercomm",
        'get_ip_path': "._new",
        'get_ip_script': 'Get_IP_v2.2.py',
        'cm_domain': 'PROD',
        'statType': [1, 3, 5, 6, 7, 8],
        'subBandId': [0, 1, 2],
        'rfboard_commands': ["show rf-components"],
        'hal_commands': ["/leap/lafe_show_status 0", "/leap/lafe_show_status 4", "/leap/lafe_show_status 5", "/leap/fafe_show_status 0", "/leap/fafe_show_status 4"]
    },
    'BC': {
        # Broadcom Configuration
        'jumpbox_hostname': 'jump.autobahn.comcast.com',
        'jumpbox_username': "svcAutobahn",
        'target_ecm_mac': '',
        'target_hostname': '192.168.2.103',
        'target_username': "root",
        'target_password': "Broadcom",
        'path': "./output",
        'run_single': True,
        'result_filename_appendix': "_test",
        'get_ip_path': ".",
        'get_ip_script': 'Get_IP_v2.2.py',
        'cm_domain': 'PROD',
        'statType': [8],
        'subBandId': [0, 1, 2],
        'rfboard_commands': ["showModuleInfo"],
        'hal_commands': ["/leap/lafe_show_status 0", "/leap/lafe_show_status 4", "/leap/lafe_show_status 5", "/leap/fafe_show_status 0", "/leap/fafe_show_status 4"]
    }
}
