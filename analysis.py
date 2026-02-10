import numpy as np
import logging
import pandas as pd
import re
import math
import os
import parsers
import struct

def complex_to_mag_db(real, imag):
    """Converts complex number components (real, imag) to magnitude in dB."""
    if not isinstance(real, list) or not isinstance(imag, list) or len(real) != len(imag):
        return []
    magnitude = np.sqrt(np.array(real)**2 + np.array(imag)**2)
    with np.errstate(divide='ignore'):
        mag_db = 20 * np.log10(magnitude)
    mag_db[np.isneginf(mag_db)] = -100
    return mag_db.tolist()

def decode_line_equalizer_coefficients(hex_string):
    """Decodes a hexadecimal string of 16-bit signed 4.12 fixed-point I/Q coefficients into a list of complex floats."""
    coefficients = []
    for i in range(0, len(hex_string), 8):
        i_hex = hex_string[i:i+4]
        q_hex = hex_string[i+4:i+8]
        if len(q_hex) < 4:
            continue
        i_unsigned = np.uint16(int(i_hex, 16))
        q_unsigned = np.uint16(int(q_hex, 16))
        i_signed = i_unsigned.view(np.int16)
        q_signed = q_unsigned.view(np.int16)
        i_float = float(i_signed) / (2**12)
        q_float = float(q_signed) / (2**12)
        coefficients.append(complex(i_float, q_float))
    return coefficients

def decode_peq_coefficients(hex_string):
    """Decodes a hexadecimal string of 16-bit signed 4.12 fixed-point I/Q coefficients into a list of complex floats."""
    coefficients = []
    for i in range(0, len(hex_string), 8):
        i_hex = hex_string[i:i+4]
        q_hex = hex_string[i+4:i+8]
        if len(q_hex) < 4:
            continue
        i_unsigned = np.uint16(int(i_hex, 16))
        q_unsigned = np.uint16(int(q_hex, 16))
        i_signed = i_unsigned.view(np.int16)
        q_signed = q_unsigned.view(np.int16)
        i_float = float(i_signed) / (2**12)
        q_float = float(q_signed) / (2**12)
        coefficients.append(complex(i_float, q_float))
    return coefficients

def decode_shaping_filter_coefficients(hex_string: str) -> list[float]:
    """
    Decodes a concatenated hex string from the shaping filter into a list of
    floating-point numbers, interpreting the source as s4.12 fixed-point format.
    """
    if not hex_string:
        return []

    chars_per_tap = 8
    num_taps = len(hex_string) // chars_per_tap
    
    if len(hex_string) % chars_per_tap != 0:
        logging.warning(f"Hex string length ({len(hex_string)}) is not a multiple of {chars_per_tap}. Decoding may be incomplete.")

    SCALING_FACTOR = 2.0**12
    coefficients = []
    
    for i in range(num_taps):
        chunk = hex_string[i*chars_per_tap : (i+1)*chars_per_tap]
        try:
            integer_value = struct.unpack('>i', bytes.fromhex(chunk))[0]
            float_value = integer_value / SCALING_FACTOR
            coefficients.append(float_value)
        except (struct.error, ValueError) as e:
            logging.error(f"Could not decode chunk '{chunk}': {e}")
            continue
            
    return coefficients

def perform_fft_on_taps(coefficients: list[float], sample_rate_mhz: float, n_fft: int = 2048):
    """
    Performs an FFT on the time-domain tap coefficients and returns frequency and magnitude data.
    """
    if not coefficients:
        return None, None

    coeffs_np = np.array(coefficients)
    fft_result = np.fft.fft(coeffs_np, n_fft)
    fft_magnitude = np.abs(fft_result)
    
    with np.errstate(divide='ignore'):
        fft_magnitude_db = 20 * np.log10(fft_magnitude)
    fft_magnitude_db[np.isneginf(fft_magnitude_db)] = -200
    fft_magnitude_db_normalized = fft_magnitude_db - np.max(fft_magnitude_db)

    freq_axis_mhz = np.fft.fftfreq(n_fft, d=1.0/sample_rate_mhz)
    
    half_point = n_fft // 2
    return freq_axis_mhz[:half_point].tolist(), fft_magnitude_db_normalized[:half_point].tolist()

def analyze_psd_delta(full_freq, full_psd, target_psd):
    """Analyzes the delta between measured and target PSD to suggest adjustments."""
    if not full_freq or not full_psd:
        return None, None
    delta = np.array(full_psd) - target_psd
    freq_np = np.array(full_freq)
    OPERATIONAL_START_MHZ = 108
    OPERATIONAL_END_MHZ = 684
    analysis_mask = (freq_np >= OPERATIONAL_START_MHZ) & (freq_np <= OPERATIONAL_END_MHZ)
    if not np.any(analysis_mask):
        logging.warning(f"Could not find frequency data within the operational tilt analysis range ({OPERATIONAL_START_MHZ}-{OPERATIONAL_END_MHZ} MHz).")
        return None, None
    freq_filtered = freq_np[analysis_mask]
    delta_filtered = delta[analysis_mask]
    try:
        if len(freq_filtered) < 2:
            logging.warning("Not enough data points for tilt analysis.")
            return None, None
        slope, _ = np.polyfit(freq_filtered, delta_filtered, 1)
    except (np.linalg.LinAlgError, TypeError):
        logging.warning("Could not perform linear regression on delta trace.")
        return None, None
    analysis_bw = freq_filtered[-1] - freq_filtered[0]
    tilt = 0 if analysis_bw == 0 else slope * analysis_bw
    eq_bw = 684 - 108
    measured_bw = freq_filtered[-1] - freq_filtered[0]
    scaling_factor = eq_bw / measured_bw if measured_bw > 0 else 1
    suggested_eq_adjust = -tilt * scaling_factor
    overall_delta = np.mean(delta)
    power_added_by_eq = suggested_eq_adjust * 0.75
    suggested_atten_adjust = overall_delta - power_added_by_eq
    return suggested_eq_adjust, suggested_atten_adjust

def process_wbfft_data(local_wbfft_paths, hal_output, constants, output_dir, sanitized_mac=None):
    """Performs the full WBFFT post-processing analysis."""
    processed_data_frames = []
    
    for measurement_name, m_config in constants.WBFFT_MEASUREMENT_CONFIGS.items():
        logging.info(f"  - Processing: {measurement_name}")
        
        wbfft_base_path = local_wbfft_paths.get(measurement_name)
        if not wbfft_base_path:
            logging.error(f"Base path for '{measurement_name}' not found. Skipping.")
            continue
            
        wbfft_dat_path = f"{wbfft_base_path}.dat"
        wbfft_df = parsers.parse_wbfft_data(wbfft_dat_path)
        
        gains = parsers.parse_hal_gains_from_output(hal_output, m_config['hal_gain_section'], m_config['hal_gain_names'])

        if wbfft_df is None or gains is None:
            logging.error(f"Cannot process {measurement_name} due to missing data.")
            continue

        # Removed the +59.5 offset
        result_series = wbfft_df['Amplitude'].copy()

        # Apply S2P corrections
        for s2p_key, operation in m_config['s2p_keys'].items():
            s2p_filename = os.path.basename(constants.S2P_FILES.get(s2p_key, ''))
            if not s2p_filename: continue

            # MODIFICATION: Prepend MAC if provided to find the correct file
            if sanitized_mac:
                s2p_filename = f"{sanitized_mac}_{s2p_filename}"

            local_s2p_path = os.path.join(output_dir, s2p_filename)
            s21_df = parsers.parse_s2p_data(local_s2p_path)
            if s21_df is not None:
                s21_df = s21_df.sort_values(by='Frequency')
                interpolated_s21_mag = np.interp(wbfft_df['Frequency'], s21_df['Frequency'], s21_df['S21_Magnitude'])
                if operation == 'subtract': result_series -= interpolated_s21_mag
                elif operation == 'add': result_series += interpolated_s21_mag
        
        # Apply additional compensation corrections
        for comp_key, operation in m_config.get('add_comp_keys', {}).items():
            comp_filename = os.path.basename(constants.COMP_FILES.get(comp_key, ''))
            if not comp_filename: continue

            # MODIFICATION: Prepend MAC if provided to find the correct file
            if sanitized_mac:
                comp_filename = f"{sanitized_mac}_{comp_filename}"

            local_comp_path = os.path.join(output_dir, comp_filename)
            comp_df = parsers.parse_s2p_data(local_comp_path)
            if comp_df is not None:
                comp_df = comp_df.sort_values(by='Frequency')
                interpolated_comp_mag = np.interp(wbfft_df['Frequency'], comp_df['Frequency'], comp_df['S21_Magnitude'])
                if operation == 'subtract': result_series -= interpolated_comp_mag
                elif operation == 'add': result_series += interpolated_comp_mag

        # Apply HAL gain corrections
        for gain_name in m_config['hal_gain_names']:
            result_series -= gains.get(gain_name, 0)
            
        # Add the specific compensation for North Port Input
        if measurement_name == 'south_port_output':
            result_series += constants.South_Port_Output_compensate

        wbfft_df[m_config['output_prefix']] = result_series
        processed_data_frames.append(wbfft_df[['Frequency', m_config['output_prefix']]].copy())

    return processed_data_frames

def _parse_freq_string(s):
    """Converts a frequency string like '111M' or '6k' to float in Hz."""
    s = s.strip().upper()
    multiplier = 1
    if s.endswith('G'): multiplier = 1e9; s = s[:-1]
    elif s.endswith('M'): multiplier = 1e6; s = s[:-1]
    elif s.endswith('K'): multiplier = 1e3; s = s[:-1]
    try:
        return float(s) * multiplier
    except ValueError:
        logging.error(f"Could not parse frequency value: {s}")
        return None

def _calculate_power_for_single_column(df, column_name, channel_definitions):
    """
    Calculates channel power for a single measurement column.
    Logic is based directly on the provided WBFFT_DS_Analyzer_v2.0.5.py script.
    """
    power_results = []
    if df.empty:
        return power_results

    for channel in channel_definitions:
        cf_hz, bw_hz = channel['cf_hz'], channel['bw_hz']
        start_freq, end_freq = cf_hz - (bw_hz / 2.0), cf_hz + (bw_hz / 2.0)
        
        channel_df = df[(df['Frequency'] >= start_freq) & (df['Frequency'] < end_freq)]
        
        power_dBmV = -math.inf
        if not channel_df.empty and not channel_df[column_name].isnull().all():
            linear_power = 10**(channel_df[column_name].dropna() / 10)
            total_linear_power = linear_power.sum()
            if total_linear_power > 0:
                power_dBmV = 10 * math.log10(total_linear_power)

        power_results.append({
            'CenterFrequency_MHz': float(f"{cf_hz/1e6:.3f}"),
            'Channel_Power_dBmV': power_dBmV
        })
    return power_results

def calculate_channel_power(df, channels_str):
    """
    Parses channel definitions and orchestrates channel power calculation for all measurement columns.
    """
    channel_definitions = []
    range_pattern = re.compile(r"([\d\.]+[KMG]?)-([\d\.]+[KMG]?)\(([\d\.]+[KMG]?)\)")
    single_pattern = re.compile(r"([\d\.]+[KMG]?)\(([\d\.]+[KMG]?)\)")
    for definition in channels_str.split(','):
        definition = definition.strip()
        if match := range_pattern.match(definition):
            start_hz, stop_hz, step_hz = map(_parse_freq_string, match.groups())
            if any(v is None for v in [start_hz, stop_hz, step_hz]): continue
            current_cf = start_hz
            while current_cf <= stop_hz:
                channel_definitions.append({'cf_hz': current_cf, 'bw_hz': step_hz})
                current_cf += step_hz
        elif match := single_pattern.match(definition):
            cf_hz, bw_hz = map(_parse_freq_string, match.groups())
            if cf_hz is not None and bw_hz is not None:
                channel_definitions.append({'cf_hz': cf_hz, 'bw_hz': bw_hz})

    if not channel_definitions:
        logging.warning("Could not parse any valid channel definitions.")
        return []

    measurement_cols = [col for col in df.columns if col != 'Frequency']
    
    all_power_results = []
    for col in measurement_cols:
        col_results = _calculate_power_for_single_column(df[['Frequency', col]], col, channel_definitions)
        
        for result in col_results:
            result['Measurement'] = col
            all_power_results.append(result)
            
    return all_power_results