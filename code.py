import time
import os
import board
import busio
import displayio
from digitalio import DigitalInOut, Direction, Pull
import adafruit_esp32spi.adafruit_esp32spi_socket as socket
from adafruit_esp32spi import adafruit_esp32spi
import adafruit_requests as requests
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text import bitmap_label
from adafruit_pyportal import PyPortal

# the current working directory (where this file is)
cwd = ("/" + __file__).rsplit("/", 1)[0]

# Add a secrets.py to your filesystem that has a
# dictionary called secrets with "ssid" and
# "password" keys with your WiFi credentials.
# DO NOT share that file or commit it into Git or other
# source control.
# pylint: disable=no-name-in-module,wrong-import-order
try:
    from secrets import secrets
except ImportError:
    print("WiFi secrets are kept in secrets.py, please add them there!")
    raise

# If you are using a board with pre-defined ESP32 Pins:
esp32_cs = DigitalInOut(board.ESP_CS)
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_reset = DigitalInOut(board.ESP_RESET)

spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

# Create the PyPortal object
pyportal = PyPortal(esp=esp, external_spi=spi)
pyportal.set_background(0x000000)
pyportal.set_backlight(1)

print("Connecting to AP...")
while not esp.is_connected:
    try:
        esp.connect_AP(secrets["ssid"], secrets["password"])
    except RuntimeError as e:
        print("could not connect to AP, retrying: ", e)
        continue
print("Connected to", str(esp.ssid, "utf-8"), "\tRSSI:", esp.rssi)

# Initialize a requests object with a socket and esp32spi interface
socket.set_interface(esp)
requests.set_socket(socket, esp)

APIURL = secrets["api_url"]
AUTHKEY = secrets["auth_key"]

DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 240

DARK_RED = 0x7f0606

PROBLEM_BG = [0x606060, # not classified
              0x0a4866, # information
              0xb2660a, # warning
              0xb24d0a, # average
              0xb22c0a, # high
              0x7f0606] # disaster

# setting up the hardware buttons
phys_blue_button = None
blue_button = DigitalInOut(board.D3)
blue_button.direction = Direction.INPUT
blue_button.pull = Pull.UP
blue_button_default_state = blue_button.value

phys_white_button = None
white_button = DigitalInOut(board.D4)
white_button.direction = Direction.INPUT
white_button.pull = Pull.UP
white_button_default_state = white_button.value

# Set up fonts
font_small = bitmap_font.load_font("/fonts/Arial-12.pcf")
font_large = bitmap_font.load_font("/fonts/Arial-18.pcf")
# preload fonts
glyphs = b"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-,.: "
font_small.load_glyphs(glyphs)
font_large.load_glyphs(glyphs)

# audio
red_alert_wav = "/sounds/red_alert.wav"

last_update = 0.0
first_run = True
max_eventid = 0
red_alert = False
host_problems = []
host_count = 0


def exists(filename):
    try:
        os.stat(filename)
        return True
    except OSError as _:
        return False

def set_image(host):
    # Set the image file for the host
    # Format is "images/host_name.bmp"
    # If file doesn't exist just ignore

    image_file_path = cwd + "images/" + host + ".bmp"
    print("Set image to", image_file_path)

    # Remove everything from the pyportal
    # DisplayIO group before starting
    for i in pyportal.splash:
        pyportal.splash.pop()

    if not host:
        return  # we're done, no icon desired
    try:
        if image_file:
            image_file.close
    except NameError:
        pass

    if exists(image_file_path):
        image_file = open(cwd + "images/" + host + ".bmp", "rb")
        image = displayio.OnDiskBitmap(image_file)
        image_sprite = displayio.TileGrid(
            image,
            pixel_shader=getattr(image, "pixel_shader", displayio.ColorConverter()),
        )
        pyportal.splash.append(image_sprite)
    else:
        print("image does not exist")


def make_host_label(text, anchor_point, anchored_position):
    # add the host name label to the display group

    print("Making label for: " + text)
    set_image(text)
    host_label = bitmap_label.Label(
        font_large,
        text=text,
        anchor_point=anchor_point,
        anchored_position=anchored_position,
        background_color=DARK_RED,
        padding_left=10,
        padding_right=board.DISPLAY.width,
        padding_bottom=19,
        padding_top=18,
    )

    pyportal.splash.append(host_label)


def make_problem_text(text, anchor_point, anchored_position, severity):
    # add a problem text item.

    print("Making problem text for: " + text)

    text_color = 0xffffff

    problem_label = bitmap_label.Label(
        font_small,
        color=text_color,
        text=text,
        anchor_point=anchor_point,
        anchored_position=anchored_position,
        background_color=PROBLEM_BG[int(severity)],
        padding_left=5,
        padding_right=board.DISPLAY.width,
        padding_bottom=5,
        padding_top=5,
    )
    pyportal.splash.append(problem_label)


def make_update_label_text(color=DARK_RED, label_text="UPDATING ISSUES"):
    """
    Create label object for labeling data values.
    It will get a background color box and appropriate padding.

    :param text: Text to show
    :param anchor_point: location anchor_point
    :param anchored_position: location anchored_position
    :return bitmap_label.Label: the Label object
    """

    print("Making update label text")
    for i in pyportal.splash:
        pyportal.splash.pop()

    pyportal.splash.append(
        bitmap_label.Label(
            font_large,
            text=label_text,
            anchor_point=(0, 0),
            anchored_position=(0, 0),
            background_color=color,
            padding_left=52,
            padding_right=DISPLAY_WIDTH,
            padding_bottom=int(DISPLAY_HEIGHT / 2 + 50),
            padding_top=int(DISPLAY_HEIGHT / 2 - 50),
        )
    )


def get_hosts_with_problems():
    global last_update

    make_update_label_text()
    print("Getting hosts with problems.")
    host_problems = []

    # get hosts with problems
    host_data = {
        "jsonrpc": "2.0",
        "method": "host.get",
        "params": {"output": ["name"], "severities": ["1", "2", "3"]},
        "auth": AUTHKEY,
        "id": 1,
    }
    response = requests.post(APIURL, json=host_data)
    problem_hosts = response.json()
    for host in problem_hosts["result"]:
        hostid = host["hostid"]
        problems = get_host_problems(host["hostid"])
        host_problems.append({"host": host, "problems": problems})
    last_update = time.monotonic()
    print("Data updated at:" + str(last_update))
    return host_problems


def get_host_problems(hostid):
    event_data = {
        "jsonrpc": "2.0",
        "method": "problem.get",
        "params": {
            "hostids": hostid,
            "output": ["eventid", "name", "severity"]
        },
        "auth": AUTHKEY,
        "id": 1,
    }
    response = requests.post(APIURL, json=event_data)
    problems = response.json()
    return problems["result"]


print("***** starting loop *****")
while True:
    host_problems = get_hosts_with_problems()
    while host_count < len(host_problems):
        host_problem = host_problems[host_count]
        make_host_label(
            text=host_problem["host"]["name"],
            anchor_point=(0, 0),
            anchored_position=(64, 0),
        )
        anchor_y = 67
        for problem in host_problem["problems"]:
            make_problem_text(
                text=problem["name"],
                anchor_point=(0.0, 0),
                anchored_position=(0, anchor_y),
                severity=problem["severity"],
            )
            anchor_y += 30

            if int(problem["eventid"]) > max_eventid:
                max_eventid = int(problem["eventid"])
                red_alert = True

            print("Event ID: " + problem["eventid"] + " >> " + str(max_eventid))

        if red_alert and not first_run:
            print("*** RED ALERT ***")
            pyportal.play_file(red_alert_wav, wait_to_finish=False)
            red_alert = False

        stamp = time.monotonic()
        # wait 10 seconds before getting again
        while (time.monotonic() - stamp) < (10):
            if white_button.value == white_button_default_state and phys_white_button:
                phys_white_button = False
            if (
                white_button.value != white_button_default_state
                and not phys_white_button
            ):
                print("White button pressed!")
                phys_white_button = True
                # host_problems = get_hosts_with_problems()
                # last_update = time.monotonic()
                break

            if blue_button.value == blue_button_default_state and phys_blue_button:
                phys_blue_button = False
            if blue_button.value != blue_button_default_state and not phys_blue_button:
                phys_blue_button = True
                print("Blue button pressed!")
                break
            # or, if they touch the screen, fetch immediately!
            # if pyportal.touchscreen.touch_point:
            # pyportal.play_file(red_alert_wav)
            # break
        if phys_white_button:
            break

        if host_count < len(host_problems) - 1:
            host_count += 1
        else:
            host_count = 0

    if (time.monotonic() - last_update) > (10 * 60) or first_run:
        if not first_run:
            host_problems = get_hosts_with_problems()
        if len(host_problems) == 0:
            make_update_label_text(color=0x00FF00, label_text="NO ISSUES")

    first_run = False
    red_alert = False
