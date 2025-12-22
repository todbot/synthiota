import displayio
import vectorio
from adafruit_display_text import bitmap_label as label
from adafruit_bitmap_font import bitmap_font

from terminalio import FONT as fnt
#from font_free_mono_8 import FONT as fnt
#fnt = bitmap_font.load_font("ProFont7-7.bdf")
    
tab_sel = None
pages = None
paramset = None
max_width = 25

def setup_display(display, aparamset):
    global paramset, pages, tab_sel
    
    paramset = aparamset
    pal = displayio.Palette(2)
    pal[0] = 0xffffff
    pal[1] = 0x000000
    
    maing = displayio.Group()
    display.root_group = maing

    tab_sel = label.Label(fnt, text="|bleh|", color=pal[0], x=20, y=7)
    hline = vectorio.Rectangle(pixel_shader=pal, width=130, height=1, x=0, y=12)
    uig = displayio.Group()
    uig.append(hline)
    uig.append(tab_sel)
    maing.append(uig)

    pages = displayio.Group()
    maing.append(pages)
    
    for i in range(paramset.nknobsets):  # number of pages
        page = displayio.Group()
        page.hidden=True
        pot_labels = displayio.Group()
        pot_vals = displayio.Group()

        y = 10
        for j in range(8):  # num pots
            pn = i*8 + j
            param = paramset.params[pn]
            y = 20 + 12 * (j % 4)  # two columns of params and
            x = 2 + 62 * int(j/4)  # four params per side
            w = 5 + int((param.val / param.span) * max_width)
            text = label.Label(fnt, text=param.name, color=pal[0], x=x, y=y)
            valline = vectorio.Rectangle(pixel_shader=pal, width=w, height=4,
                                         x=x+30, y=y-2)
            pot_labels.append(text)
            pot_vals.append(valline)
            
        page.append(pot_labels)
        page.append(pot_vals)
        pages.append(page)
    
def update_page(i=0,oldi=0):
    print("oldi:", oldi, "i:",i)
    pages[oldi].hidden = True
    pages[i].hidden = False
    tab_sel.text = "|" + "page" + str(i) + "|"
    tab_sel.x = 0 + 36 * i

def update_page_vals(params):
    idx = paramset.idx
    for i in range(8):
        param = paramset.params[idx*8 +i]
        pages[idx][1][i].width = 5 + int((param.val / param.span) * max_width)


