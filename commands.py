import verifiers
import parsers

def generate_command_sequences(settings, constants):
    """Dynamically builds the command sequences from the settings file."""
    
    general_settings = settings.get("General settings", {})
    upgradefw_timeout = general_settings.get("upgradefw_timeout", 600)
    alignment_timeout = general_settings.get("alignment_timeout", 120)

    spec_settings = settings.get("spectrum", {})
    ds_settings = settings.get("ds-profile", {})
    us_settings = settings.get("us-profile", {})
    upgradefw_settings = settings.get("upgradefw", {})
    backoff_settings = settings.get("north-afe-backoff", {})
    atteneq_settings = settings.get("atten-and-eq", {})

    spectrum_sequence = [{'command': 'configure spectrum', 'validation_string': 'spectrum-allocation', 'delay_before_prompt': 1.5}]
    if spec_settings.get("us-extended-end-freq", "") != "":
        spectrum_sequence.append({'command': f"us-extended-end-freq {spec_settings['us-extended-end-freq']}", 'validation_string': 'is set from'})
    if spec_settings.get("subband_0_mode", "") != "":
        spectrum_sequence.append({'command': f"subband 0 {spec_settings['subband_0_mode']}", 'validation_string': 'is set from'})
    if spec_settings.get("subband_1_mode", "") != "":
        spectrum_sequence.append({'command': f"subband 1 {spec_settings['subband_1_mode']}", 'validation_string': 'is set from'})
    if spec_settings.get("subband_2_mode", "") != "":
        spectrum_sequence.append({'command': f"subband 2 {spec_settings['subband_2_mode']}", 'validation_string': 'is set from'})

    spectrum_sequence.extend([
        {'command': 'commit', 'validation_string': 'spectrum allocation is saved in non-vol memory'},
																																																	  
        {'command': 'configure ds-freq-override', 'validation_string': None}
    ])

    if spec_settings.get('ds_override_enabled', True):
        spectrum_sequence.append({'command': 'enabled true', 'validation_string': ['FDX RepeaterSettings block added', 'FDX RepeaterSettings block already present']})
        if spec_settings.get("ds-start-freq-cc", "") != "":
            spectrum_sequence.append({'command': f"ds-start-freq-cc {spec_settings['ds-start-freq-cc']}", 'validation_string': 'DownstreamStartFreqHzCC set to'})
    else:
        spectrum_sequence.append({'command': 'enabled false', 'validation_string': ['FDX RepeaterSettings block removed', 'FDX RepeaterSettings block is not present']})
    
    spectrum_sequence.extend([
        {'command': 'commit', 'validation_string': 'Checksum matches. Configuration committed.'},
																																						
        {'command': 'exit', 'validation_string': None}
    ])

    rf_components_sequence = [{'command': "rf-components", 'validation_string': None}]
    if atteneq_settings.get("legacy-input-atten", "") != "":
        rf_components_sequence.append({'command': f"legacy-us-input-atten main {atteneq_settings['legacy-input-atten']}", 'validation_string': 'main legacy-us-input-atten is set from'})
    if atteneq_settings.get("ds-output-atten", "") != "":
        rf_components_sequence.append({'command': f"ds-output-atten {atteneq_settings['ds-output-atten']}", 'validation_string': 'ds-output-attenuation-db is set from'})
    if atteneq_settings.get("ds-output-eq", "") != "":
        rf_components_sequence.append({'command': f"ds-output-eq {atteneq_settings['ds-output-eq']}", 'validation_string': 'ds-output-eq-db is set from'})
    if atteneq_settings.get("us-fdx-atten", "") != "":
        rf_components_sequence.append({'command': f"us-fdx-atten {atteneq_settings['us-fdx-atten']}", 'validation_string': 'us-fdx-attenuation-db is set from'})
    if atteneq_settings.get("us-fdx-eq", "") != "":
        rf_components_sequence.append({'command': f"us-fdx-eq {atteneq_settings['us-fdx-eq']}", 'validation_string': 'us-fdx-equalization-db is set from'})
    
    rf_components_sequence.extend([
																																												   
        {'command': 'exit', 'validation_string': None}
    ])

    sequences = {
        "showModuleInfo": [{'command': 'showModuleInfo', 'parser': parsers.parse_module_info}],
        "show_spectrum": [
            {'command': 'configure spectrum', 'validation_string': 'spectrum-allocation', 'delay_before_prompt': 1.5},
            {'command': 'show configuration', 'parser': parsers.parse_spectrum_config, 'wait_for_string': '-----------------------------------------'},
            {'command': 'exit', 'validation_string': None}
        ],
        "show_ds-profile":[
            {'command': f"configure ds-profile south", 'validation_string': 'ds-profile-south', 'delay_before_prompt': 1.5},
            {'command': 'show configuration', 'parser': parsers.parse_ds_profile_config, 'wait_for_string': '------------------------------------------'},
            {'command': 'exit', 'validation_string': None}
        ],
        "show_us-profile":[
            {'command': f"configure us-profile south", 'validation_string': 'us-profile-south', 'delay_before_prompt': 1.5},
            {'command': 'show configuration', 'parser': parsers.parse_us_profile_config, 'wait_for_string': '------------------------------------------'},
            {'command': 'exit', 'validation_string': None}
        ],
        "show_north-afe-backoff":[
            {'command': "configure north-port", 'validation_string': "north-port", 'delay_before_prompt': 1.5},
            {'command': 'show configuration', 'parser': parsers.parse_backoff_config, 'wait_for_string': '-----------------------------------------'},
            {'command': 'exit', 'validation_string': None}
        ],
        "show_rf_components": [
            {'command': "rf-components", 'validation_string': None},
            {'command': 'show rf-components', 'parser': parsers.parse_rf_components_config, 'wait_for_string': 'pa-bias'},
            {'command': 'exit', 'validation_string': None}
        ],
        "show_alignment": [
            {'command': 'configure alignment', 'validation_string': None},
            {'command': 'show alignment-status', 'parser': parsers.parse_alignment_status, 'wait_for_string': 'NET:'},
            {'command': 'exit', 'validation_string': None}
        ],
        "show_fafe": [
            {'command': 'debug hal\r\nlog_config --off', 'validation_string': 'Connected', 'prompt_marker': constants.PROMPT_MARKERS['hal'], 'wait_for_prompt': False, 'delay_before_prompt': 1},
            {'command': '/leap/fafe_show_status 0', 'parser': parsers.parse_afe_status, 'wait_for_string': 'NcInputPower', 'prompt_marker': constants.PROMPT_MARKERS['hal'], 'clip_key': 'NcClipCount'},
            {'command': '/leap/fafe_show_status 4', 'parser': parsers.parse_afe_status, 'wait_for_string': 'NcInputPower', 'prompt_marker': constants.PROMPT_MARKERS['hal'], 'clip_key': 'NcClipCount'},
            {'command': '/leap/lafe_show_status 0', 'parser': parsers.parse_afe_status, 'wait_for_string': 'RxInputPower', 'prompt_marker': constants.PROMPT_MARKERS['hal'], 'clip_key': 'RxClipCount'},
            {'command': '/leap/lafe_show_status 4', 'parser': parsers.parse_afe_status, 'wait_for_string': 'RxInputPower', 'prompt_marker': constants.PROMPT_MARKERS['hal'], 'clip_key': 'RxClipCount'},
            {'command': '/leap/lafe_show_status 5', 'parser': parsers.parse_afe_status, 'wait_for_string': 'RxInputPower', 'prompt_marker': constants.PROMPT_MARKERS['hal'], 'clip_key': 'RxClipCount'},
            {'command': '\x04\n', 'validation_string': None, 'prompt_marker': constants.PROMPT_MARKERS['default']}
        ],
        "get_nc_input_power": [
            {'command': 'debug hal\r\nlog_config --off', 'validation_string': 'Connected', 'prompt_marker': constants.PROMPT_MARKERS['hal'], 'wait_for_prompt': False, 'delay_before_prompt': 1},
            {'command': '/leap/fafe_show_status 4', 'parser': parsers.parse_afe_status, 'wait_for_string': 'NcInputPower', 'prompt_marker': constants.PROMPT_MARKERS['hal']},
            {'command': '\x04\n', 'validation_string': None, 'prompt_marker': constants.PROMPT_MARKERS['default']}
        ],
        "configure_spectrum": spectrum_sequence,
        "configure_ds-profile":[
            {'command': f"configure ds-profile south", 'validation_string': 'ds-profile-south', 'delay_before_prompt': 1.5},
            {'command': f"start-freq {ds_settings.get('start-freq', '')}", 'validation_string': 'min-frequency-hertz" is set from'},
            {'command': f"end-freq {ds_settings.get('end-freq', '')}", 'validation_string': 'max-frequency-hertz" is set from'},
            {'command': f"start-power {round(float(ds_settings.get('start-power', 0)), 1)}", 'validation_string': '"ds-power-min-freq-dbmv" is set from'},
            {'command': f"end-power {round(float(ds_settings.get('end-power', 0)), 1)}", 'validation_string': 'ds-power-max-freq-dbmv'},
            {'command': 'commit', 'validation_string': 'applied local configuration'},
																																																		   
            {'command': 'exit', 'validation_string': None}
        ],
        "commit_ds-profile":[
            {'command': f"configure ds-profile south", 'validation_string': 'ds-profile-south', 'delay_before_prompt': 1.5},
            {'command': 'commit', 'validation_string': 'applied local configuration'},
																																																		   
            {'command': 'exit', 'validation_string': None}
        ],
        "configure_us-profile":[
            {'command': f"configure us-profile south", 'validation_string': 'us-profile-south', 'delay_before_prompt': 1.5},
            {'command': f"rlsp {us_settings.get('rlsp', '')}", 'validation_string': 'rlsp is set from'},
            {'command': 'commit', 'validation_string': 'applied local configuration'},
																																																		   
            {'command': 'exit', 'validation_string': None}
        ],
        "commit_us-profile":[
            {'command': f"configure us-profile south", 'validation_string': 'us-profile-south', 'delay_before_prompt': 1.5},
            {'command': 'commit', 'validation_string': 'applied local configuration'},
																																																		   
            {'command': 'exit', 'validation_string': None}
        ],
        "run_alignment":[
            {'command': "configure alignment", 'validation_string': None, 'prompt_marker': constants.PROMPT_MARKERS['default']},
            {'command': "start-ds1", 'validation_string': 'Completed DS1 alignment', 'prompt_marker': constants.PROMPT_MARKERS['default'], 'timeout': alignment_timeout},
            {'command': 'start-ds2', 'validation_string': 'Completed DS2 alignment', 'prompt_marker': constants.PROMPT_MARKERS['default'], 'timeout': alignment_timeout},
            {'command': 'start-ds3', 'validation_string': 'Completed DS3 alignment', 'prompt_marker': constants.PROMPT_MARKERS['default'], 'timeout': alignment_timeout},
            {'command': 'start-us', 'validation_string': 'Completed US alignment', 'prompt_marker': constants.PROMPT_MARKERS['default'], 'timeout': alignment_timeout},
            {'command': 'exit', 'validation_string': None}
        ],
        "reset":[ {'command': "reset", 'validation_string': "reset"} ],
        "upgradefw":[ {'command': f"upgradefw http {upgradefw_settings.get('host', '')} {upgradefw_settings.get('filename', '')}", 'validation_string': "Successfully upgraded the image", 'timeout': upgradefw_timeout} ],
        "generate_key":[ {'command': "configure crypto key generate rsa", 'validation_string': "SSH host rsa private key has beensuccessfully imported."} ],
        "configure_north-afe-backoff":[
            {'command': "configure north-port", 'validation_string': "north-port", 'delay_before_prompt': 1.5},
            {'command': f"north-afe-backoff {backoff_settings.get('backoff', '')}", 'validation_string': 'north-afe-backoff-db is set from'},
            {'command': 'commit', 'validation_string': 'north-port param is saved in non-vol memory'},
																																																			
            {'command': 'exit', 'validation_string': None}
        ],
        "configure_rf_components": rf_components_sequence,
        "tg_start":[
            {'command': 'debug hal\r\nlog_config --off', 'validation_string': 'Connected', 'prompt_marker': constants.PROMPT_MARKERS['hal'], 'wait_for_prompt': False, 'delay_before_prompt': 1},
            {'command': '/usrptr/write_ofdma 0x15c4   0x0', 'validation_string': 'Success', 'prompt_marker': constants.PROMPT_MARKERS['hal']},
            {'command': '/usrptr/write_ofdma 0x15c8   0x0', 'validation_string': 'Success', 'prompt_marker': constants.PROMPT_MARKERS['hal']},
            {'command': '/usrptr/write_ofdma 0x15cc   0x1000000', 'validation_string': 'Success', 'prompt_marker': constants.PROMPT_MARKERS['hal']},
            {'command': '/usrptr/write_ofdma 0x15d0   0x9077800', 'validation_string': 'Success', 'prompt_marker': constants.PROMPT_MARKERS['hal']},
            {'command': '/usrptr/write_ofdma 0x15d4   0x7f0', 'validation_string': 'Success', 'prompt_marker': constants.PROMPT_MARKERS['hal']},
            {'command': '/usrptr/write_ofdma 0x181a44 0x40000', 'validation_string': 'Success', 'prompt_marker': constants.PROMPT_MARKERS['hal'], 'wait_for_prompt': False, 'delay_before_prompt': 1.5},
            {'command': '\x04\n', 'validation_string': None, 'prompt_marker': constants.PROMPT_MARKERS['default']}
        ],
        "tg_stop":[
            {'command': 'debug hal\r\nlog_config --off', 'validation_string': 'Connected', 'prompt_marker': constants.PROMPT_MARKERS['hal'], 'wait_for_prompt': False, 'delay_before_prompt': 1},
            {'command': '/usrptr/write_ofdma 0x15c4   0x0', 'validation_string': 'Success', 'prompt_marker': constants.PROMPT_MARKERS['hal']},
            {'command': '/usrptr/write_ofdma 0x15c8   0x0', 'validation_string': 'Success', 'prompt_marker': constants.PROMPT_MARKERS['hal']},
            {'command': '/usrptr/write_ofdma 0x15cc   0x1000000', 'validation_string': 'Success', 'prompt_marker': constants.PROMPT_MARKERS['hal']},
            {'command': '/usrptr/write_ofdma 0x15d0   0xA077800', 'validation_string': 'Success', 'prompt_marker': constants.PROMPT_MARKERS['hal']},
            {'command': '/usrptr/write_ofdma 0x15d4   0x7f0', 'validation_string': 'Success', 'prompt_marker': constants.PROMPT_MARKERS['hal']},
            {'command': '/usrptr/write_ofdma 0x181a44 0x40000', 'validation_string': 'Success', 'prompt_marker': constants.PROMPT_MARKERS['hal'], 'wait_for_prompt': False, 'delay_before_prompt': 1.5},
            {'command': '\x04\n', 'validation_string': None, 'prompt_marker': constants.PROMPT_MARKERS['default']}
        ],
        # --- New and Renamed WBFFT Tasks ---
        "get_wbfft": [],
        "get_wbfft_hal_gains": [
            {'command': 'debug hal\r\nlog_config --off', 'validation_string': 'Connected', 'prompt_marker': constants.PROMPT_MARKERS['hal'], 'wait_for_prompt': False, 'delay_before_prompt': 1},
            {'command': '/leap/fafe_show_status 4', 'wait_for_string': 'NcInputPower', 'prompt_marker': constants.PROMPT_MARKERS['hal'], 'delay_before_prompt': 0.5},
            {'command': '/leap/lafe_show_status 0', 'wait_for_string': 'RxInputPower', 'prompt_marker': constants.PROMPT_MARKERS['hal'], 'delay_before_prompt': 0.5},
            {'command': '/leap/lafe_show_status 4', 'wait_for_string': 'RxInputPower', 'prompt_marker': constants.PROMPT_MARKERS['hal'], 'delay_before_prompt': 0.5},
            {'command': '\x04\n', 'validation_string': None, 'prompt_marker': constants.PROMPT_MARKERS['default']}
        ],
        "get_eq": [], 
        "get_sf": [],
        "adjust_north-afe-backoff": [], 
        "get_ec": [],
        "get_us_psd": [],
        "adjust_us-fdx-settings": [],
        "adjust_rlsp_diff": [],
        "get_clipping": [],
        "wait": [],
    }
    return sequences
