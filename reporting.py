import webbrowser
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots
import os
import numpy as np
from datetime import datetime
import logging

import matplotlib.pyplot as plt
import matplotlib.mlab as mlab
import io
import base64
import matplotlib
from matplotlib import font_manager
import mpld3

# Setup custom font for matplotlib (if needed)
font_dirs = ["resources/fonts"]  # The path to the custom font file.
font_files = font_manager.findSystemFonts(fontpaths=font_dirs)

for font_file in font_files:
    font_manager.fontManager.addfont(font_file)

plt.rcParams['font.family'] = 'ComcastNewVision'  # Use the custom font for all plots

def generate_eq_html_report(mac_address, us_coeffs, ds_coeffs, output_filename, freq_resolution_mhz):
    """Generates an interactive HTML plot using Plotly for the decoded coefficients."""
    fig = go.Figure()
    if us_coeffs:
        us_freq = np.arange(len(us_coeffs)) * freq_resolution_mhz
        us_amp_db = 20 * np.log10(np.abs(us_coeffs), where=(np.abs(us_coeffs) > 0), out=np.full(len(us_coeffs), -np.inf))
        fig.add_trace(go.Scatter(x=us_freq, y=us_amp_db, mode='lines', name='Upstream Pre-Equalizer'))
    if ds_coeffs:
        ds_freq = np.arange(len(ds_coeffs)) * freq_resolution_mhz
        ds_amp_db = 20 * np.log10(np.abs(ds_coeffs), where=(np.abs(ds_coeffs) > 0), out=np.full(len(ds_coeffs), -np.inf))
        fig.add_trace(go.Scatter(x=ds_freq, y=ds_amp_db, mode='lines', name='Downstream Line Equalizer'))
    fig.update_layout(
        title=f'Equalizer Frequency Response for {mac_address}',
        xaxis_title='Frequency (MHz)',
        yaxis_title='Amplitude (dB)',
        template='plotly_white',
        height=900
    )
    try:
        pio.write_html(fig, output_filename)
        #open html
        abs_path = os.path.abspath(output_filename)
        # print(f"{abs_path}")
        url = f"file://{abs_path}"
        webbrowser.open_new_tab(url)        
        logging.info(f"[{mac_address}] Interactive HTML plot saved to {output_filename}")
    except Exception as e:
        logging.error(f"[{mac_address}] Failed to save interactive HTML plot: {e}")

def generate_sf_html_report(mac_address, taps_data, freq_data, output_dir):
    """Generates an interactive HTML plot for the shaping filter analysis."""
    fig = make_subplots(
        rows=2, cols=1, 
        subplot_titles=("Time Domain: Filter Taps (Impulse Response)", "Frequency Domain: Magnitude Response")
    )

    tap_numbers = list(range(len(taps_data)))
    fig.add_trace(go.Scatter(
        x=tap_numbers,
        y=taps_data,
        mode='markers',
        name='Taps'
    ), row=1, col=1)
    
    for i, val in enumerate(taps_data):
        fig.add_shape(
            type="line",
            x0=i, y0=0, x1=i, y1=val,
            line=dict(color="grey", width=1),
            row=1, col=1
        )

    freq_axis_mhz, magnitude_db = freq_data
    fig.add_trace(go.Scatter(
        x=freq_axis_mhz,
        y=magnitude_db,
        mode='lines',
        name='Frequency Response'
    ), row=2, col=1)

    fig.update_layout(
        title_text=f'Shaping Filter Analysis for {mac_address}',
        template='plotly_white',
        height=900,
        showlegend=False
    )
    
    fig.update_xaxes(title_text="Tap Number", row=1, col=1)
    fig.update_yaxes(title_text="Coefficient Amplitude", row=1, col=1)
    fig.update_xaxes(title_text="Frequency (MHz)", row=2, col=1)
    # --- MODIFICATION: Removed the fixed 'range' parameter to enable auto-scaling ---
    fig.update_yaxes(title_text="Normalized Magnitude (dB)", row=2, col=1)

    sanitized_mac = mac_address.replace(':', '')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_filename = os.path.join(output_dir, f"{sanitized_mac}_get_sf_data_{timestamp}.html")

    try:
        pio.write_html(fig, output_filename)
        abs_path = os.path.abspath(output_filename)
        logging.info(f"Opening interactive WBFFT report in web browser: {abs_path}")
        # print(f"{abs_path}")
        url = f"file://{abs_path}"
        webbrowser.open_new_tab(url)
        logging.info(f"[{mac_address}] Interactive SF report saved to {output_filename}")
        return output_filename
    except Exception as e:
        logging.error(f"[{mac_address}] Failed to save interactive SF report: {e}")
        return None

def generate_ec_html_report(mac_address, decoded_data, output_dir):
    """Generates interactive HTML plots for the decoded EC data."""
    sanitized_mac = mac_address.replace(':', '')
    timestamp = datetime.now().strftime('%Ym%d_%H%M%S')
    
    fig_coef = make_subplots(rows=2, cols=1, subplot_titles=("Time Coef (IFFT)", "Freq Coef"))
    
    if 2 in decoded_data:
        for subBandId, data in decoded_data[2].items():
            fig_coef.add_trace(go.Scatter(x=data.get('distance_ft', []), y=data.get('values_db', []), mode='lines', name=f"Time Coef sb{subBandId}"), row=1, col=1)
    
    if 1 in decoded_data:
        full_freq_x, full_freq_y = [], []
        for subBandId, data in decoded_data[1].items():
            full_freq_x.extend(data.get('frequencies_mhz', []))
            full_freq_y.extend(data.get('values', []))
        fig_coef.add_trace(go.Scatter(x=full_freq_x, y=full_freq_y, mode='lines', name="Freq Coef"), row=2, col=1)
        
    fig_coef.update_layout(title=f'Echo Cancellation Coefficients for {mac_address}', template='plotly_white', height=900)
    fig_coef.update_xaxes(title_text="Distance (ft)", row=1, col=1)
    fig_coef.update_xaxes(title_text="Frequency (MHz)", row=2, col=1)
    
    # If caller passed a file path (ends with .html) use it directly for the coef report.
    # Otherwise treat `output_dir` as a directory and construct the filename.
    if str(output_dir).lower().endswith('.html'):
        coef_filename = str(output_dir)
        base_no_ext = coef_filename[:-5]
        psd_filename = f"{base_no_ext}_psd.html"
    else:
        coef_filename = os.path.join(output_dir, f"{sanitized_mac}_get_ec_coefs_data_{timestamp}.html")
    pio.write_html(fig_coef, coef_filename)
    #open html
    abs_path = os.path.abspath(coef_filename)
    # print(f"{abs_path}")
    url = f"file://{abs_path}"
    webbrowser.open_new_tab(url)
    logging.info(f"[{mac_address}] Saved EC Coefficient HTML report to {coef_filename}")

    fig_psd = go.Figure()
    psd_types = {5: "Echo PSD", 6: "Residual Echo PSD", 7: "Downstream PSD", 8: "Upstream PSD"}
    for statsType, name in psd_types.items():
        if statsType in decoded_data:
            full_x, full_y = [], []
            for subBandId, data in decoded_data[statsType].items():
                full_x.extend(data.get('frequencies_mhz', []))
                full_y.extend(data.get('values', []))
            fig_psd.add_trace(go.Scatter(x=full_x, y=full_y, mode='lines', name=name))
    fig_psd.update_layout(title=f'EC PSD Metrics for {mac_address}', xaxis_title='Frequency (MHz)', yaxis_title='Power (dBmV/100kHz)', template='plotly_white', height=900)
    # If psd_filename wasn't set above (output_dir was directory), build it now.
    if 'psd_filename' not in locals():
        psd_filename = os.path.join(output_dir, f"{sanitized_mac}_get_ec_psd_data_{timestamp}.html")
    pio.write_html(fig_psd, psd_filename)
    #open html
    abs_path = os.path.abspath(psd_filename)
    # print(f"{abs_path}")
    url = f"file://{abs_path}"
    webbrowser.open_new_tab(url)    
    logging.info(f"[{mac_address}] Saved EC PSD Metrics HTML report to {psd_filename}")

def generate_ec_html_report_matlab(mac_address, decoded_data, output_dir):
    """Generates HTML reports for EC data using matplotlib (prefer mpld3 for interactivity).

    If `mpld3` is installed the function writes fully interactive HTML (zoom, pan, tooltips).
    Otherwise it falls back to embedding PNGs (base64) in HTML files.
    Returns tuple: (coef_html_path, psd_html_path)
    """
    # Ensure non-interactive backend for file generation when needed
    try:
        matplotlib.use('Agg')
    except Exception:
        pass

    sanitized_mac = mac_address.replace(':', '')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # --- Coefficients figure ---
    fig1, axes = plt.subplots(2, 1, figsize=(10, 8))

    # Time Coef (IFFT)
    if 2 in decoded_data:
        for subBandId, data in decoded_data[2].items():
            x = data.get('distance_ft', [])
            y = data.get('values_db', [])
            if x and y:
                axes[0].plot(x, y, label=f"sb{subBandId}")
    axes[0].set_title(f'Time Coef (IFFT) for {mac_address}')
    axes[0].set_xlabel('Distance (ft)')
    axes[0].set_ylabel('Amplitude (dB)')
    axes[0].legend(loc='best')

    # Freq Coef
    if 1 in decoded_data:
        full_freq_x, full_freq_y = [], []
        for subBandId, data in decoded_data[1].items():
            full_freq_x.extend(data.get('frequencies_mhz', []))
            full_freq_y.extend(data.get('values', []))
        if full_freq_x and full_freq_y:
            axes[1].plot(full_freq_x, full_freq_y, '-k')
    axes[1].set_title(f'Freq Coef for {mac_address}')
    axes[1].set_xlabel('Frequency (MHz)')
    axes[1].set_ylabel('Coefficient')

    fig1.tight_layout()

    coef_filename = os.path.join(output_dir, f"{sanitized_mac}_get_ec_coefs_data_{timestamp}.html")
    try:
        if mpld3 is not None:
            # Use mpld3 to generate interactive HTML
            coef_html = mpld3.fig_to_html(fig1)
            with open(coef_filename, 'w', encoding='utf-8') as f:
                f.write(coef_html)
        else:
            # Fallback: embed PNG as base64
            buf1 = io.BytesIO()
            fig1.savefig(buf1, format='png')
            buf1.seek(0)
            img1_b64 = base64.b64encode(buf1.read()).decode('ascii')
            coef_html = f"""
<html>
<head><title>EC Coefficients - {sanitized_mac}</title></head>
<body>
<h2>Echo Cancellation Coefficients for {mac_address}</h2>
<img src="data:image/png;base64,{img1_b64}" alt="EC Coefficients">
</body>
</html>
"""
            with open(coef_filename, 'w', encoding='utf-8') as f:
                f.write(coef_html)
        logging.info(f"[{mac_address}] Saved EC Coefficient HTML report to {coef_filename}")
    except Exception as e:
        logging.error(f"[{mac_address}] Failed to save EC Coefficient HTML report: {e}")
    finally:
        plt.close(fig1)

    # --- PSD figure ---
    fig2, ax2 = plt.subplots(1, 1, figsize=(10, 5))
    psd_types = {5: "Echo PSD", 6: "Residual Echo PSD", 7: "Downstream PSD", 8: "Upstream PSD"}
    any_plotted = False
    for statsType, name in psd_types.items():
        if statsType in decoded_data:
            full_x, full_y = [], []
            for subBandId, data in decoded_data[statsType].items():
                full_x.extend(data.get('frequencies_mhz', []))
                full_y.extend(data.get('values', []))
            if full_x and full_y:
                ax2.plot(full_x, full_y, label=name)
                any_plotted = True
    ax2.set_title(f'EC PSD Metrics for {mac_address}')
    ax2.set_xlabel('Frequency (MHz)')
    ax2.set_ylabel('Power (dBmV/100kHz)')
    if any_plotted:
        ax2.legend(loc='best')

    fig2.tight_layout()

    psd_filename = os.path.join(output_dir, f"{sanitized_mac}_get_ec_psd_data_{timestamp}.html")
    try:
        if mpld3 is not None:
            psd_html = mpld3.fig_to_html(fig2)
            with open(psd_filename, 'w', encoding='utf-8') as f:
                f.write(psd_html)
        else:
            buf2 = io.BytesIO()
            fig2.savefig(buf2, format='png')
            buf2.seek(0)
            img2_b64 = base64.b64encode(buf2.read()).decode('ascii')
            psd_html = f"""
<html>
<head><title>EC PSD - {sanitized_mac}</title></head>
<body>
<h2>EC PSD Metrics for {mac_address}</h2>
<img src="data:image/png;base64,{img2_b64}" alt="EC PSD">
</body>
</html>
"""
            with open(psd_filename, 'w', encoding='utf-8') as f:
                f.write(psd_html)
        logging.info(f"[{mac_address}] Saved EC PSD Metrics HTML report to {psd_filename}")
    except Exception as e:
        logging.error(f"[{mac_address}] Failed to save EC PSD HTML report: {e}")
    finally:
        plt.close(fig2)

    # Open generated files
    try:
        webbrowser.open_new_tab(f"file://{os.path.abspath(coef_filename)}")
    except Exception:
        pass
    try:
        webbrowser.open_new_tab(f"file://{os.path.abspath(psd_filename)}")
    except Exception:
        pass

    return coef_filename, psd_filename

def generate_us_psd_report(mac_address, us_psd_data, target_psd, output_dir, eq_adjust=None, atten_adjust=None, child_mac_address=None):
    """Generates an interactive HTML plot for the US PSD, Target PSD, and Delta."""
    sanitized_mac = mac_address.replace(':', '')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, subplot_titles=("Upstream PSD vs. Target", "Delta (Measured - Target)"))
    
    full_freq, full_psd = [], []
    for subBandId in sorted(us_psd_data.keys()):
        data = us_psd_data[subBandId]
        full_freq.extend(data.get('frequencies_mhz', []))
        full_psd.extend(data.get('values', []))

    fig.add_trace(go.Scatter(x=full_freq, y=full_psd, mode='lines', name='Measured US PSD'), row=1, col=1)
    fig.add_trace(go.Scatter(x=full_freq, y=[target_psd] * len(full_freq), mode='lines', name='Target PSD', line=dict(dash='dash', color='red')), row=1, col=1)
    
    delta = np.array(full_psd) - target_psd
    delta_filtered = [d if abs(d) <= 25 else None for d in delta]
    fig.add_trace(go.Scatter(x=full_freq, y=delta_filtered, mode='lines', name='Delta', line=dict(color='green')), row=2, col=1)

    title_text = f'Upstream PSD Analysis for Parent: {mac_address}'
    if child_mac_address:
        title_text += f'<br>Reference Child: {child_mac_address}'
    if eq_adjust is not None and atten_adjust is not None:
        title_text += f"<br><b>Suggested EQ Adjust: {eq_adjust:.1f} dB | Suggested Atten Adjust: {atten_adjust:.1f} dB</b>"
    
    fig.update_layout(title=title_text, template='plotly_white', height=900)
    fig.update_yaxes(title_text="Power (dBmV/100kHz)", row=1, col=1)
    fig.update_yaxes(title_text="Delta (dB)", row=2, col=1)
    fig.update_xaxes(title_text="Frequency (MHz)", row=2, col=1)
    
    filename_prefix = f"parent_{sanitized_mac}"
    if child_mac_address:
        sanitized_child = child_mac_address.replace(':', '')
        filename_prefix += f"_child_{sanitized_child}"
    output_filename = os.path.join(output_dir, f"{filename_prefix}_get_us_psd_report_{timestamp}.html")
    try:
        pio.write_html(fig, output_filename)
        #open html
        abs_path = os.path.abspath(output_filename)
        # print(f"{abs_path}")
        url = f"file://{abs_path}"
        webbrowser.open_new_tab(url)        
        logging.info(f"[{mac_address}] Interactive US PSD report saved to {output_filename}")
        return output_filename
    except Exception as e:
        logging.error(f"[{mac_address}] Failed to save interactive US PSD report: {e}")
        return None

def generate_wbfft_report(mac_address, final_df, power_results, output_dir):
    """Generates an interactive HTML plot for the combined WBFFT results."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.15,
                        subplot_titles=("WBFFT Power Spectrum", "Calculated Channel Power"))

    # Plot 1: WBFFT Power Spectrum
    for col in final_df.columns:
        if col != 'Frequency':
            fig.add_trace(go.Scatter(x=final_df['Frequency'] / 1e6, y=final_df[col],
                                     mode='lines', name=col), row=1, col=1)

    # Plot 2: Channel Power
    if power_results:
        grouped_power_data = {}
        for item in power_results:
            measurement_name = item.get('Measurement')
            if not measurement_name:
                continue
            
            if measurement_name not in grouped_power_data:
                grouped_power_data[measurement_name] = {'x': [], 'y': []}
            
            power_val = item.get('Channel_Power_dBmV')
            if power_val is not None and np.isfinite(power_val):
                grouped_power_data[measurement_name]['x'].append(item.get('CenterFrequency_MHz'))
                grouped_power_data[measurement_name]['y'].append(power_val)
        
        for name, data in grouped_power_data.items():
            if data['x']:
                fig.add_trace(
                    go.Scatter(
                        x=data['x'],
                        y=data['y'],
                        mode='lines+markers',
                        name=f"{name} (Channel Power)"
                    ),
                    row=2, col=1
                )

    fig.update_layout(
        title_text=f'WBFFT Analysis for {mac_address}',
        template='plotly_white',
        height=900
    )
    fig.update_yaxes(title_text="Power (dBmV/100kHz)", row=1, col=1)
    fig.update_yaxes(title_text="Channel Power (dBmV)", row=2, col=1)
    fig.update_xaxes(title_text="Frequency (MHz)", row=2, col=1)

    sanitized_mac = mac_address.replace(':', '')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_filename = os.path.join(output_dir, f"{sanitized_mac}_get_wbfft_data_{timestamp}.html")

    try:
        pio.write_html(fig, output_filename)
        abs_path = os.path.abspath(output_filename)
        logging.info(f"Opening interactive WBFFT report in web browser: {abs_path}")
        # print(f"{abs_path}")
        url = f"file://{abs_path}"
        webbrowser.open_new_tab(url)
        logging.info(f"[{mac_address}] Interactive WBFFT report saved to {output_filename}")

        return output_filename
    except Exception as e:
        logging.error(f"[{mac_address}] Failed to save interactive WBFFT report: {e}")
        return None
