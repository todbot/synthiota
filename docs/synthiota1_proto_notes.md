
# Synthiota1 Proto 15 Jun 2025 Notes

## Overall

- All the parts of the board seem to work!


## PCB

- Sliders suck, they're too small
  - Can somewhat fix it in software by increasing the charge current, 
   `mpr121s[1]._write_register_byte(adafruit_mpr121.MPR121_CONFIG1, 0x20)  # default, 2*16uA charge current? `
   - solution: make sliders taller? ditch sliders entirely? 

- Layout too cramped vertically, towards the pot LED area

- Missing Play/Pause button? 
  - new 1 Sep 2025 version adds another touch button for this




## Software

- Maybe model after the Bass Station II

    - patch parameters:
      - osc1 octave
      - osc1 mod env depth
      - osc1 lfo depth
      - osc1 waveform
      - amp env attack
      - amp env release
      - amp env sustain
      - amp env decay
      
      - filt type
      - filt freq
      - filt resonance
      - filt env attack
      - filt env release
      - filt env sustain
      - filt env decay
      
      - delay
      - overdrive
      - reverb
      - detune

  

