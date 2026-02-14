# --- Define all possible prompt markers ---
PROMPT_MARKERS = {
    "default": ">$",
    "hal": "hal>"
}

# --- WBFFT Analysis Task Settings ---
WBFFT_SETTINGS = {
    'startFreq': 0,
    'endFreq': 1250000000,
    'runDuration': 1000,
    'aggrPeriod': 1000,
    'triggerCount': 0,
    'outputFormat': "FreqDomainPower",
    'outputScale': 6,
    'fftSize': 16384,
    'windowMode': "Blackman-Harris",
    'averagingMode': "Time",
    'samplingRate': 1647000000,
}

# Added compensation value for South Port Output
South_Port_Output_compensate = -4

WBFFT_REMOTE_PATHS = {
    "s2p_remote_path": "/run/data/calibration/",
    "additional_comp_remote_path": "/mnt/nonvol_active/"
}

WBFFT_CHANNEL_DEFINITIONS = '99M-1215M(6M)'

S2P_FILES = {
    'H21': 'H21.s2p',
    'H35': 'H35.s2p',
    'H65': 'H65.s2p'
}

COMP_FILES = {
    'SP_DTS_OUT': "SP_DTS_OUT_1p2G_Mode.DAT",
    'SF_WBFFT_ADC': "SF_WBFFT_ADC_DP0_Factory_1p2G_Mode.txt"
}

WBFFT_MEASUREMENT_CONFIGS = {
    'north_port_input': {
        'adcSelect': 'ADC_NPU',
        'hal_gain_section': 'lafe_show_status 0', 'hal_gain_names': ('PreAdcRxGain', 'PostAdcRxGain'),
        's2p_keys': {'H21': 'subtract'},
        'add_comp_keys': {},
        'output_prefix': 'North_Port_Input'
    },
    'south_port_output': {
        'adcSelect': 'ADC_DP0',
        'hal_gain_section': 'lafe_show_status 4', 'hal_gain_names': ('PreAdcRxGain', 'PostAdcRxGain'),
        's2p_keys': {'H35': 'subtract', 'H65': 'add'},
        'add_comp_keys': {'SP_DTS_OUT': 'add', 'SF_WBFFT_ADC': 'subtract'},
        'output_prefix': 'South_Port_Output'
    },
    'ds_afe_input': {
        'adcSelect': 'ADC_NPD',
        'hal_gain_section': 'fafe_show_status 4', 'hal_gain_names': ('PreAdcNcGain', 'PostAdcNcGain'),
        's2p_keys': {},
        'add_comp_keys': {},
        'output_prefix': 'DS_AFE_Input'
    }
}

