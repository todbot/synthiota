import time
import board
import busio
import fourwire
import displayio
import vectorio
import adafruit_displayio_sh1106

disp_sclk = board.GP10
disp_mosi = board.GP11
disp_res  = board.GP12
disp_dc   = board.GP13

dw,dh = 132,64

displayio.release_displays()

spi = busio.SPI(clock=disp_sclk, MOSI=disp_mosi)
display_bus = fourwire.FourWire(spi, command = disp_dc, reset=disp_res)
display = adafruit_displayio_sh1106.SH1106(display_bus, width=dw, height=dh, colstart=3)

maing = displayio.Group()
display.root_group = maing

palette = displayio.Palette(2)
palette[0] = 0x000000
palette[1] = 0xffffff
maing.append(vectorio.Rectangle(pixel_shader=palette, width=100, height=60, x=10,y=10,color_index=1))
maing.append(vectorio.Circle(pixel_shader=palette, radius=25, x=60,y=30, color_index=0))

while True:
    x = int(time.monotonic()*20) % 20 
    print("hi", x, time.monotonic())
    maing[0].x =x 
    time.sleep(0.1)
