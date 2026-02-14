def verify_configuration(parsed_config, settings_section):
    """Compares parsed device config against the original settings."""
    mismatches = []
    for key, expected_value in settings_section.items():
        if expected_value == "" or key in ['ds_override_enabled', 'ds-start-freq-cc', 'port']:
            continue
        device_key = key.replace('_', '-') if not key.startswith('subband_') else key
        device_value = parsed_config.get(device_key)
        if device_value is None:
            mismatches.append({"parameter": key, "expected": expected_value, "found": "Not Found"})
            continue
        try:
            if float(device_value) != float(expected_value):
                mismatches.append({"parameter": key, "expected": expected_value, "found": float(device_value)})
        except (ValueError, TypeError):
            if str(device_value).lower() != str(expected_value).lower():
                mismatches.append({"parameter": key, "expected": expected_value, "found": device_value})
    return (False, mismatches) if mismatches else (True, "All settings match.")

def verify_ds_freq_override_config(parsed_config, settings_section):
    """Verifies the 'Status' from the ds-freq-override sub-mode."""
    expected_status = 'enabled' if settings_section.get('ds_override_enabled', False) else 'disabled'
    found_status = parsed_config.get('status')
    if found_status and found_status.lower() == expected_status.lower():
        return True, "Override status matches."
    else:
        return False, [{"parameter": "status", "expected": expected_status, "found": found_status or "Not Found"}]

def verify_rf_components_config(parsed_config, settings_section):
    """Compares parsed rf-components config against the original settings."""
    mismatches = []
    device_type = settings_section.get('device_type')
    key_map = {
        'ds-output-atten': 'ds-output-attenuation-db',
        'ds-output-eq': 'ds-output-eq-db',
        'us-fdx-atten': 'us-fdx-attenuation-db',
        'us-fdx-eq': 'us-fdx-equalization-db'
    }
    for settings_key, expected_value in settings_section.items():
        if expected_value == "" or settings_key == 'device_type':
            continue
        keys_to_check = []
        if settings_key == 'legacy-input-atten':
            keys_to_check.append('legacy-us-input-atten main')
            if device_type == 'MB':
                keys_to_check.append('legacy-us-input-atten aux')
        elif settings_key in key_map:
            keys_to_check.append(key_map[settings_key])
        else:
            continue
        for device_key in keys_to_check:
            device_value = parsed_config.get(device_key)
            if device_value is None:
                mismatches.append({"parameter": device_key, "expected": expected_value, "found": "Not Found"})
                continue
            try:
                if float(device_value) != float(expected_value):
                    mismatches.append({"parameter": device_key, "expected": expected_value, "found": float(device_value)})
            except (ValueError, TypeError):
                 mismatches.append({"parameter": device_key, "expected": expected_value, "found": device_value})
    return (False, mismatches) if mismatches else (True, "All settings match.")
