# SPDX-FileCopyrightText: Copyright (c) 2025 Tod Kurt
# SPDX-License-Identifier: MIT
"""
`mapped_pot_controller.py`
================================================================================

`Parameter` is a configuration for a single controlled value.

`MappedPotController` maps those parameters to knobs and back again.

10 Feb 2026 - @todbot / Tod Kurt
"""

import array

class Parameter:
    """
    Configuration for a single control parameter.

    Maps 16-bit hardware integers (0-65535) to a defined real-world range
    and handles UI formatting and callbacks.
    
    :param min_val: Lower bound of range
    :param max_val: Upper bound of range
    :param label: Display name (e.g. "Cutoff")
    :param decimals: Float precision
    :param options: List of discrete strings for option-style controls
    :param callback: Function called on change
    """
    def __init__(self, min_val, max_val, label="", decimals=2, options=None, callback=None):
        self.min = min_val
        self.max = max_val
        self.label = label
        self.decimals = decimals
        self.options = options
        self.callback = callback
        self.is_int = isinstance(min_val, int) and isinstance(max_val, int)
        self.slope = (max_val - min_val) / 65535

    def map_value(self, raw_int):
        """Converts 0-65535 to real-world range."""
        val = (raw_int * self.slope) + self.min
        return int(val + 0.5) if self.is_int else val

    def unmap_value(self, real_val):
        """Converts real-world value back to 0-65535."""
        if self.max == self.min: return 0
        raw = (real_val - self.min) / self.slope
        return int(max(0, min(65535, raw)))

    def format_value(self, raw_int):
        """Formats the value for a UI display."""
        if self.options:
            idx = (raw_int * (len(self.options) - 1)) // 65535
            return self.options[idx]
        val = self.map_value(raw_int)
        return str(val) if self.is_int else f"{val:.{self.decimals}f}"


class MappedPotController:
    """
    Logic engine for multi-bank potentiometer control mapped to Paramter values.

    Handles noise filtering (hysteresis) and provides two modes for 
    switching between virtual banks without parameter jumps.

    :param num_pots: Number of physical potentiometers.
    :param num_banks: Number of virtual layers (banks) available.
    :param mode: Sets interaction logic (MODE_RELATIVE or MODE_TAKEOVER).
    :param window: Hysteresis window under which changes are ignored.
    """
    
    MODE_TAKEOVER = 0
    MODE_RELATIVE = 1

    def __init__(self, all_configs, mode=1, window=800):
        self.configs = all_configs
        self.num_banks = len(all_configs)
        self.num_pots = len(all_configs[0])
        self.mode = mode
        self.window = window

        # State storage
        self.banks = [[0] * self.num_pots for _ in range(self.num_banks)]
        self.values = [0.0] * self.num_pots 
        self.current_bank = 0

        # Use array.array for hardware tracking. 
        # These are pre-allocated contiguous memory blocks that don't create new objects.
        # 'H' is unsigned short (16-bit)
        self.last_raw = array.array('H', [0] * self.num_pots)
        self.last_reported = array.array('H', [0] * self.num_pots)
        self.active_flags = [False] * self.num_pots
        
        # Pre-calculate the denominator for normalization
        self._norm_denom = 65535 - (window << 1)

    def load_preset(self, bank_idx, real_values):
        """
        Loads values into a bank. Triggers callbacks for affected parameters.
        :param bank_idx: The index of the parameter bank to set.
        :param curr_potvals: A list of real values for those parameters.
        """
        for i, val in enumerate(real_values):
            cfg = self.configs[bank_idx][i]
            raw_int = cfg.unmap_value(val)
            self.banks[bank_idx][i] = raw_int
            
            if cfg.callback:
                cfg.callback(val)

            if bank_idx == self.current_bank:
                self.active_flags[i] = False
                self.last_reported[i] = raw_int
                self.values[i] = val

    def get_display_data(self, pot_idx):
        cfg = self.configs[self.current_bank][pot_idx]
        raw = self.banks[self.current_bank][pot_idx]
        return cfg.label, cfg.format_value(raw)

    def switch_bank(self, bank_idx, curr_potvals):
        """
        Switches the active bank and synchronizes hardware history.
        Does not trigger callbacks for non-active banks.
        :param bank_idx: The index of the bank to switch to.
        :param curr_potvals: The current raw 16-bit readings from the pots.
        """
        self.current_bank = bank_idx
        for i in range(self.num_pots):
            self.active_flags[i] = False
            self.last_raw[i] = curr_potvals[i]
            raw_in_bank = self.banks[bank_idx][i]
            self.last_reported[i] = raw_in_bank
            self.values[i] = self.configs[bank_idx][i].map_value(raw_in_bank)            
                
    def update(self, curr_potvals):
        """
        Processes new hardware readings and updates bank data.
        Will trigger Parameter callbacks for changed pots.
        :param curr_potvals: List of current raw 16-bit readings.
        :return: A bitmask where each bit represents a pot that changed.
        """
        changed_mask = 0
        bank = self.banks[self.current_bank]
        
        # Local cache of constants to avoid 'self' lookups in the loop
        win = self.window
        denom = self._norm_denom
        mode_rel = self.MODE_RELATIVE

        for i in range(self.num_pots):
            raw = curr_potvals[i]
            
            # Hysteresis check
            if abs(raw - self.last_raw[i]) < win:
                continue
            
            # Optimization 3: Fixed-Point Normalization (No floats)
            if raw <= win: 
                adj = 0
            elif raw >= (65535 - win): 
                adj = 65535
            else:
                # Integer math: (numerator * 65535) // denominator
                adj = ((raw - win) * 65535) // denom

            if not self.active_flags[i]:
                if self.mode == mode_rel:
                    self.last_reported[i] = adj
                    self.active_flags[i] = True
                    self.last_raw[i] = raw
                    continue
                else: 
                    if abs(adj - bank[i]) < 1500:
                        self.active_flags[i] = True
            
            if self.active_flags[i]:
                old_raw_val = bank[i]
                if self.mode == self.MODE_TAKEOVER:
                    bank[i] = adj
                else: 
                    # Optimization 4: Combined Integer Ratio Calculation
                    # Replaces float 'ratio' with (diff * available_range) // avail_phys
                    diff = adj - self.last_reported[i]
                    if diff > 0:
                        avail_phys = 65535 - (adj - diff)
                        move = (diff * (65535 - bank[i])) // avail_phys if avail_phys > 0 else 0
                    else:
                        avail_phys = adj - diff
                        move = (diff * bank[i]) // avail_phys if avail_phys > 0 else 0
                    
                    new_val = bank[i] + move
                    bank[i] = max(0, min(65535, new_val))


                if bank[i] != old_raw_val:
                    cfg = self.configs[self.current_bank][i]
                    new_mapped_val = cfg.map_value(bank[i])
                    
                    if new_mapped_val != self.values[i]:
                        changed_mask |= (1 << i)
                        self.values[i] = new_mapped_val
                        if cfg.callback:
                            cfg.callback(new_mapped_val)

            self.last_reported[i] = adj
            self.last_raw[i] = raw
            
        return changed_mask



