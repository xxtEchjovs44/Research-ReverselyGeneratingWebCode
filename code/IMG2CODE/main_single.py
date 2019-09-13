import merge
import ocr
import ui

from file_utils import time_start, timer_end

is_ctpn = False
is_uied = True
is_merge = False

PATH_IMG_INPUT = 'data\\input\\13.png'
PATH_LABEL_COMPO = 'data\\output\\compo.json'
PATH_LABEL_TEXT = 'data\\output\\ocr.txt'
PATH_CTPN_DRAWN = 'data\\output\\ctpn.png'
PATH_UIED_DRAWN = 'data\\output\\uied.png'
PATH_UIED_BIN = 'data\\output\\gradient.png'
PATH_MERGE = 'data\\output\\merged.png'
PATH_COMPONENT = 'data\\output\\components'

start = time_start()

if is_ctpn:
    ocr.ctpn(PATH_IMG_INPUT, PATH_LABEL_TEXT, PATH_CTPN_DRAWN)
if is_uied:
    ui.uied(PATH_IMG_INPUT, PATH_LABEL_COMPO, PATH_UIED_DRAWN, PATH_UIED_BIN)
if is_merge:
    merge.incorporate(PATH_IMG_INPUT, PATH_LABEL_COMPO, PATH_LABEL_TEXT, PATH_MERGE, is_clip=True, clip_path=PATH_COMPONENT)

timer_end(start)
