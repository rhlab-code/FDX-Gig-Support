# Unified Amplifier Control Library
# Version: 1.0
#
# Description:
# This library provides a class-based structure for controlling different
# types of amplifiers. A base class, AmpControl, defines the common interface,
# while subclasses (CommscopeAmp, ComcastAmp, SercommAmp) implement the
# specific SSH command sequences for each device.

import time
import re
import numpy as np

class AmpControl:
    def complex_to_mag_db(self, real, imag):
        """Converts complex data (real and imaginary parts) to magnitude in dB."""
        data = []
        for re, im in zip(real,imag):
            # Calculate magnitude using Euclidean distance (sqrt(real^2 + imag^2))
            magnitude = np.sqrt(re**2 + im**2)
            # Convert magnitude to dB (20 * log10(magnitude))
            magnitude_db = 20 * np.log10(magnitude)
            data.append(magnitude_db)
        return data
    def split_list_in_half(self, lst):
        """Splits a list into two halves."""
        midpoint = len(lst) // 2  # Use floor division to get the middle index
        first_half = lst[:midpoint]
        second_half = lst[midpoint:]
        return [first_half, second_half]
    """Base class for amplifier control."""
    def _get_output(self, channel, wait_time=0.25):
        """Waits for and reads data from the SSH channel."""
        while not channel.recv_ready():
            time.sleep(wait_time)
        return channel.recv(4096).decode("utf-8")

    def hal_comm(self, channel, command, prompt=">", wait_time=10):
        """Placeholder for HAL command execution. Must be overridden by subclasses."""
        raise NotImplementedError("hal_comm method must be implemented by a subclass.")

    def rf_comm(self, channel, command, prompt=">", wait_time=10):
        """Placeholder for RF board command execution. Must be overridden by subclasses."""
        raise NotImplementedError("rf_comm method must be implemented by a subclass.")

class CommscopeAmp(AmpControl):
    """Handles communication with CommScope amplifiers."""
    def hal_comm(self, channel, command, prompt=">", wait_time=10):
        start_time = time.time()
        channel.send('\r\n')
        output = self._get_output(channel)
        print(output)
        
        while True:
            if "hal>" in output:
                channel.send(f'{command} \r\n')
                full_output = ""
                while True:
                    time.sleep(0.5)
                    if channel.recv_ready():
                        full_output += channel.recv(128000).decode("utf-8")
                    if prompt in full_output:
                        print(full_output)
                        return full_output
                    if time.time() > start_time + wait_time:
                        raise TimeoutError(f"Timeout waiting for prompt '{prompt}' after command '{command}'")
                    channel.send(f'\r\n')
                    
            elif "FDX-AMP>" in output:
                channel.send('hal\n')
            elif "FDX-AMP(" in output:
                channel.send('exit\n')
            elif "login:" in output:
                channel.send('cli\n')
            elif "Password:" in output:
                channel.send('cli\n')
            elif "# " in output:
                channel.send('exit\n')
            else:
                channel.send('\r\n')
            
            output = self._get_output(channel)
            print(output)

    def rf_comm(self, channel, command, prompt="FDX-AMP(rfboard)>", wait_time=10):
        start_time = time.time()
        channel.send('\r\n')
        output = self._get_output(channel)
        print(output)
        
        while True:
            if "FDX-AMP(rfboard)>" in output:
                channel.send(f'{command} \r\n')
                full_output = ""
                while True:
                    time.sleep(0.5)
                    if channel.recv_ready():
                        full_output += channel.recv(128000).decode("utf-8")
                    if prompt in full_output:
                        print(full_output)
                        return full_output
                    if time.time() > start_time + wait_time:
                        raise TimeoutError(f"Timeout waiting for prompt '{prompt}' after command '{command}'")
                    
            elif "FDX-AMP>" in output:
                channel.send('rfboard\n')
            elif "hal>" in output:
                channel.send('exit\n')
            elif "login:" in output:
                channel.send('cli\n')
            elif "Password:" in output:
                channel.send('cli\n')
            elif "# " in output:
                channel.send('exit\n')
            else:
                channel.send('\r\n')
            
            output = self._get_output(channel)
            print(output)

class ComcastAmp(AmpControl):
    """Handles communication with Comcast (RDK) amplifiers."""
    def hal_comm(self, channel, command, prompt=">", wait_time=10):
        start_time = time.time()
        channel.send('\r\n')
        output = self._get_output(channel)
        print(output)

        while True:
            if "hal>" in output:
                channel.send(f'{command} \r\n')
                full_output = ""
                while True:
                    time.sleep(0.5)
                    if channel.recv_ready():
                        full_output += channel.recv(128000).decode("utf-8")
                    if prompt in full_output:
                        print(full_output)
                        return full_output
                    if time.time() > start_time + wait_time:
                        raise TimeoutError(f"Timeout waiting for prompt '{prompt}' after command '{command}'")
                    channel.send(f'\r\n')
                    
            elif "FDX-AMP>" in output:
                channel.send('debug hal\n')
            elif "FDX-AMP(" in output:
                channel.send('exit\n')
            elif "login:" in output:
                channel.send('admin\n')
            elif "Password:" in output:
                channel.send('AMPadmin\n')
            elif "# " in output:
                channel.send('exit\n')
            else:
                channel.send('\r\n')

            output = self._get_output(channel)
            print(output)

    def rf_comm(self, channel, command, prompt="FDX-AMP(rf-components)>", wait_time=10):
        start_time = time.time()
        channel.send('\r\n')
        output = self._get_output(channel)
        print(output)

        while True:
            if "FDX-AMP(rf-components)>" in output:
                channel.send(f'{command} \r\n')
                full_output = ""
                while True:
                    time.sleep(0.5)
                    if channel.recv_ready():
                        full_output += channel.recv(128000).decode("utf-8")
                    if prompt in full_output:
                        print(full_output)
                        return full_output
                    if time.time() > start_time + wait_time:
                        raise TimeoutError(f"Timeout waiting for prompt '{prompt}' after command '{command}'")
                    
            elif "FDX-AMP>" in output:
                channel.send('rf-components\n')
            elif "hal>" in output:
                channel.send('\x04\n') # Ctrl+D to exit HAL
            elif "login:" in output:
                channel.send('admin\n')
            elif "Password:" in output:
                channel.send('AMPadmin\n')
            elif "# " in output:
                channel.send('exit\n')
            else:
                channel.send('\r\n')

            output = self._get_output(channel)
            print(output)

class SercommAmp(AmpControl):
    """Handles communication with Sercomm amplifiers."""
    def hal_comm(self, channel, command, prompt=">", wait_time=10):
        start_time = time.time()
        channel.send('\r\n')
        output = self._get_output(channel)
        print(output)

        while True:
            if "hal>" in output:
                channel.send(f'{command} \r\n')
                full_output = ""
                while True:
                    time.sleep(0.5)
                    if channel.recv_ready():
                        full_output += channel.recv(128000).decode("utf-8")
                    if prompt in full_output:
                        print(full_output)
                        return full_output
                    if time.time() > start_time + wait_time:
                        raise TimeoutError(f"Timeout waiting for prompt '{prompt}' after command '{command}'")
                    channel.send(f'\r\n')
                    
            elif "scamp:~# " in output:
                channel.send('clish -x /etc/amp/cli/\n\n')
                time.sleep(0.5) # Give it time to enter the mode
                channel.send('debug hal\n')
            elif "FDX-AMP>" in output:
                channel.send('debug hal\n')
            elif "hal/wbfft>" in output:
                channel.send('cd ..\n')
            else:
                channel.send('\r\n')

            output = self._get_output(channel)
            print(output)

    def rf_comm(self, channel, command, prompt="~#", wait_time=10):
        start_time = time.time()
        channel.send('\r\n')
        output = self._get_output(channel)
        print(output)

        while True:
            if "scamp:~# " in output:
                channel.send(f'{command} \r\n')
                full_output = ""
                while True:
                    time.sleep(0.5)
                    if channel.recv_ready():
                        full_output += channel.recv(128000).decode("utf-8")
                    if prompt in full_output:
                        print(full_output)
                        return full_output
                    if time.time() > start_time + wait_time:
                        raise TimeoutError(f"Timeout waiting for prompt '{prompt}' after command '{command}'")
                    
            elif "hal>" in output:
                channel.send('\x04\n') # Ctrl+D to exit HAL
            else:
                channel.send('\r\n')
            
            output = self._get_output(channel)
            print(output)

class BroadcomAmp(AmpControl):
    """Handles communication with Sercomm amplifiers."""
    def hal_comm(self, channel, command, prompt="~#", wait_time=10):
        start_time = time.time()
        channel.send('\r\n')
        output = self._get_output(channel)
        print(output)

        while True:
            if "scamp:~# " in output:
                channel.send(f'sc_brcmcli -S amphal -c "{command}" \r\n')   # type
                time.sleep(0.5)
                channel.send('\r\n')
                full_output = ""
                while True:
                    time.sleep(0.5)
                    if channel.recv_ready():
                        full_output += channel.recv(128000).decode("utf-8")
                    if prompt in full_output:
                        print(full_output)
                        return full_output
                    if time.time() > start_time + wait_time:
                        raise TimeoutError(f"Timeout waiting for prompt '{prompt}' after command '{command}'")
                    channel.send(f'\r\n')
                    
            elif "scamp:~# " in output:
                channel.send('clish -x /etc/amp/cli/\n\n')
                time.sleep(0.5) # Give it time to enter the mode
                channel.send('debug hal\n')
            elif "FDX-AMP>" in output:
                channel.send('debug hal\n')
            elif "hal/wbfft>" in output:
                channel.send('cd ..\n')
            else:
                channel.send('\r\n')

            output = self._get_output(channel)
            print(output)

    def rf_comm(self, channel, command, prompt="~#", wait_time=10):
        start_time = time.time()
        channel.send('\r\n')
        output = self._get_output(channel)
        print(output)

        while True:
            if "scamp:~# " in output:
                channel.send(f'{command} \r\n')
                full_output = ""
                while True:
                    time.sleep(0.5)
                    if channel.recv_ready():
                        full_output += channel.recv(128000).decode("utf-8")
                    if prompt in full_output:
                        print(full_output)
                        return full_output
                    if time.time() > start_time + wait_time:
                        raise TimeoutError(f"Timeout waiting for prompt '{prompt}' after command '{command}'")
                    
            elif "hal>" in output:
                channel.send('\x04\n') # Ctrl+D to exit HAL
            else:
                channel.send('\r\n')
            
            output = self._get_output(channel)
            print(output)
