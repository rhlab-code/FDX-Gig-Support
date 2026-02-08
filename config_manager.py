# Unified Configuration Manager for WBFFT Analyzer
# Version: 1.0
#
# Description:
# This file consolidates all device-specific configurations into a single,
# easy-to-manage dictionary. The main script will load the appropriate
# configuration from this file based on the --image command-line argument.

CONFIGURATIONS = {
    'CS': {
        # CommScope Configuration
        'jumpbox_hostname': 'jump.autobahn.comcast.com',
        'jumpbox_username': "svcAutobahn",
        'target_ecm_mac': '24:a1:86:09:26:bc',
        'target_hostname': '',
        'target_username': "cli",
        'target_password': "cli",
        'result_path': "./output",
        'result_filename_appendix': "",
        'get_ip_path': ".",
        'get_ip_script': 'Get_IP_v2.2.py',
        'cm_domain': 'PROD',
        's2p_remote_path': "/run/data/calibration/",
        's2p_filenames': {
            'H21': 'H21.s2p',
            'H35': 'H35.s2p',
            'H65': 'H65.s2p'
        },
        'additional_comp_remote_path': '/tmp/',
        'additional_comp_filenames': {},
        'startFreq': 96000000,
        'endFreq': 1218000000,
        'runDuration': 1000,
        'aggrPeriod': 1000,
        'triggerCount': 0,
        'outputFormat': "FreqDomainDb",
        'fftSize': 16384,
        'windowMode': "Blackman-Harris",
        'averagingMode': "Time",
        'samplingRate': 1647000000,
        'rfboard_commands': ["setNorthPortSwitch Downstream", "showModuleInfo"],
        'hal_commands': ["/leap/lafe_show_status 0", "/leap/lafe_show_status 4", "/leap/fafe_show_status 0", "/leap/fafe_show_status 4"]
    },
    'CC': {
        # Comcast (RDK) Configuration
        'jumpbox_hostname': 'jump.autobahn.comcast.com',
        'jumpbox_username': "svcAutobahn",
        'target_ecm_mac': '24:a1:86:09:65:fc',
        'target_hostname': '',
        'target_username': "admin",
        'target_password': "AMPadmin",
        'result_path': "./output",
        'result_filename_appendix': "",
        'get_ip_path': ".",
        'get_ip_script': 'Get_ip_v2.2.py',
        'cm_domain': 'PROD',
        's2p_remote_path': "/run/data/calibration/",
        's2p_filenames': {
            'H21': 'H21.s2p',
            'H35': 'H35.s2p',
            'H65': 'H65.s2p'
        },
        'additional_comp_remote_path': '/tmp/',
        'additional_comp_filenames': {},
        'startFreq': 96000000,
        'endFreq': 1218000000,
        'runDuration': 1000,
        'aggrPeriod': 1000,
        'triggerCount': 0,
        'outputFormat': "FreqDomainDb",
        'fftSize': 16384,
        'windowMode': "Blackman-Harris",
        'averagingMode': "Time",
        'samplingRate': 1647000000,
        'rfboard_commands': ["north-port-switch-path ds", "showModuleInfo"],
        'hal_commands': ["/leap/lafe_show_status 0", "/leap/lafe_show_status 4", "/leap/lafe_show_status 5", "/leap/fafe_show_status 0", "/leap/fafe_show_status 4"]
    },
    'SC': {
        # Sercomm Configuration
        'jumpbox_hostname': 'jump.autobahn.comcast.com',
        'jumpbox_username': "svcAutobahn",
        'target_ecm_mac': '',
        'target_hostname': '2001:0558:6034:000C:1090:5905:E54B:CB40',
        'target_username': "root",
        'target_password': "",
        'result_path': "./output",
        'result_filename_appendix': "",
        'get_ip_path': ".",
        'get_ip_script': 'Get_ip_v2.2.py',
        'cm_domain': 'PROD',
        's2p_remote_path': "/mnt/sc_nonvol/s2p_files/",
        'additional_comp_remote_path': "/mnt/nonvol_active/",
        's2p_filenames': {
            'H21': 'H21.s2p',
            'H35': 'H35_1p2G.s2p',
            'H65': 'mode3/H65_1p2G.s2p'
        },
        'additional_comp_filenames': {
            'SP_DTS_OUT': "SP_DTS_OUT_1p2G_Mode.DAT",
            'SF_WBFFT_ADC': "SF_WBFFT_ADC_DP0_Factory_1p2G_Mode.txt"
        },
        'startFreq': 96000000,
        'endFreq': 1218000000,
        'runDuration': 1000,
        'aggrPeriod': 1000,
        'triggerCount': 0,
        'outputFormat': "FreqDomainDb",
        'fftSize': 16384,
        'windowMode': "Blackman-Harris",
        'averagingMode': "Time",
        'samplingRate': 1647000000,
        'rfboard_init_command': "tempsensor.sh init",
        'rfboard_commands': ["tempsensor.sh read", "sc_rfboard_cli set_np_monitor_input ds", "sc_rfboard_cli get_pa_current 0", "sc_rfboard_cli get_attenuation 0", "sc_rfboard_cli get_var_tilt 0"],
        'hal_commands': ["/leap/lafe_show_status 0", "/leap/lafe_show_status 4", "/leap/lafe_show_status 5", "/leap/fafe_show_status 0", "/leap/fafe_show_status 4"],
        'brcm_commands' : ['dump_avs']
    }
}

