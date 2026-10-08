from tkinter import BooleanVar, StringVar, TclError, colorchooser, filedialog
from functools import lru_cache
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageTk
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import customtkinter as ctk
import json
import math
import os
import queue
import random
import threading
import time

FOLDER = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(FOLDER, "settings.json")
PICTURE_FILE = os.path.join(FOLDER, "profile.png")
SIZE = 320  # size of the uploaded square picture in pixels
COLORS = ["#0200fe", "#7000fe", "#10f21c", "#ff15f8", "#eefe05", "#fa116b", "#9B2335", "#E08119", "#F96714", "#00539C", "#00A591", "#006E51"]
INSTAGRAM = ["#feda75", "#fa7e1e", "#d62976", "#962fbf", "#4f5bd5"]

# (hour, top color, bottom color) - the sky blends between these through the day
DAYTIME = [
    (0, "#0b1026", "#2b1055"),
    (5, "#2b1055", "#7597de"),
    (7, "#ff9a8b", "#ff6a88"),
    (10, "#56ccf2", "#2f80ed"),
    (14, "#4facfe", "#00f2fe"),
    (18, "#f5af19", "#f12711"),
    (20, "#c94b4b", "#4b134f"),
    (22, "#141e30", "#243b55"),
    (24, "#0b1026", "#2b1055"),
]

DEFAULTS = {
    "background_mode": "random",  # random | color | gradient | daytime | image
    "background_color": "#00539C",
    "gradient_color1": "#7000fe",
    "gradient_color2": "#fa116b",
    "gradient_style": "linear",  # linear | radial
    "gradient_angle": 45,
    "gradient_random": False,
    "background_images": [],
    "image_order": "random",  # random | order
    "image_fit": "fill",  # fill | fit
    "darken": 0,
    "blur": 0,
    "vignette": 0,
    "grayscale": False,
    "font": os.path.join(FOLDER, "TCCEB.TTF"),
    "text_color": "#ffffff",
    "outline": True,
    "time_format": "%H:%M",
    "time_size": 100,
    "time_x": 0,
    "time_y": -25,
    "date_show": True,
    "date_format": "%d-%b-%y",
    "date_size": 52,
    "date_x": 0,
    "date_y": 45,
    "interval": 60,
}


def load_settings():
    settings = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            settings.update(json.load(f))
    except (OSError, ValueError):
        pass
    return settings


def save_settings():
    with lock:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)


@lru_cache(maxsize=32)
def get_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size)


@lru_cache(maxsize=16)
def background_image(path, fit):
    image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if fit == "fit":
        # whole image on top of a blurred, zoomed copy of itself
        back = ImageOps.fit(image, (SIZE, SIZE), Image.LANCZOS).filter(ImageFilter.GaussianBlur(18))
        front = ImageOps.contain(image, (SIZE, SIZE), Image.LANCZOS)
        back.paste(front, ((SIZE - front.width) // 2, (SIZE - front.height) // 2))
        return back
    return ImageOps.fit(image, (SIZE, SIZE), Image.LANCZOS)


def rotated_ramp(ramp, size, angle):
    """Rotate a left-to-right ramp image and crop a size x size square from the middle."""
    # the ramp must span the square's extent along the angle so both ends reach full color
    rad = math.radians(angle)
    span = math.ceil(size * (abs(math.cos(rad)) + abs(math.sin(rad)))) + 4
    ramp = ramp.resize((span, span), Image.BICUBIC).rotate(angle, Image.BICUBIC, expand=True)
    left = (ramp.width - size) // 2
    top = (ramp.height - size) // 2
    return ramp.crop((left, top, left + size, top + size))


@lru_cache(maxsize=64)
def gradient(color1, color2, style, angle):
    if style == "radial":
        mask = Image.radial_gradient("L").resize((SIZE, SIZE), Image.BICUBIC)
    else:
        mask = rotated_ramp(Image.linear_gradient("L"), SIZE, angle)
    return Image.composite(Image.new("RGB", (SIZE, SIZE), color2), Image.new("RGB", (SIZE, SIZE), color1), mask)


def multi_gradient(colors, size, angle):
    """Linear gradient through several hex colors."""
    strip = Image.new("RGB", (256, 1))
    for x in range(256):
        position = x / 255 * (len(colors) - 1)
        i = min(int(position), len(colors) - 2)
        strip.putpixel((x, 0), mix(colors[i], colors[i + 1], position - i))
    return rotated_ramp(strip, size, angle)


def mix(color1, color2, amount):
    a, b = ImageColor.getrgb(color1), ImageColor.getrgb(color2)
    return tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def daytime_colors(hour):
    for (h1, top1, bottom1), (h2, top2, bottom2) in zip(DAYTIME, DAYTIME[1:]):
        if h1 <= hour < h2:
            amount = (hour - h1) / (h2 - h1)
            return mix(top1, top2, amount), mix(bottom1, bottom2, amount)
    return ImageColor.getrgb(DAYTIME[0][1]), ImageColor.getrgb(DAYTIME[0][2])


@lru_cache(maxsize=1)
def vignette_mask():
    return Image.radial_gradient("L").resize((SIZE, SIZE), Image.BICUBIC)


def new_pick(s, index=None):
    """Random choices for one picture; index walks the images in order."""
    images = s["background_images"]
    image = None
    if images:
        image = images[index % len(images)] if index is not None and s["image_order"] == "order" else random.choice(images)
    return {"color": random.choice(COLORS), "pair": tuple(random.sample(COLORS, 2)), "image": image}


def make_background(s, pick):
    mode = s["background_mode"]
    if mode == "image" and s["background_images"]:
        try:
            return background_image(pick["image"] or random.choice(s["background_images"]), s["image_fit"]).copy()
        except OSError:
            pass
    if mode == "color":
        return Image.new("RGB", (SIZE, SIZE), s["background_color"])
    if mode == "gradient":
        colors = pick["pair"] if s["gradient_random"] else (s["gradient_color1"], s["gradient_color2"])
        return gradient(*colors, s["gradient_style"], s["gradient_angle"]).copy()
    if mode == "daytime":
        now = time.localtime()
        return gradient(*daytime_colors(now.tm_hour + now.tm_min / 60), "linear", 0).copy()
    return Image.new("RGB", (SIZE, SIZE), pick["color"])


def apply_effects(image, s):
    if s["grayscale"]:
        image = ImageOps.grayscale(image).convert("RGB")
    if s["blur"]:
        image = image.filter(ImageFilter.GaussianBlur(s["blur"]))
    if s["darken"]:
        image = Image.blend(image, Image.new("RGB", image.size, "black"), s["darken"] / 100)
    if s["vignette"]:
        mask = vignette_mask().point(lambda v: v * s["vignette"] // 100)
        image = Image.composite(Image.new("RGB", image.size, "black"), image, mask)
    return image


def format_now(fmt):
    try:
        return time.strftime(fmt)
    except ValueError:
        return fmt


def render(s, pick=None):
    """Render the clock picture from settings dict s."""
    image = apply_effects(make_background(s, pick or new_pick(s)), s)
    draw = ImageDraw.Draw(image)
    lines = [("time", format_now(s["time_format"]))]
    if s["date_show"]:
        lines.append(("date", format_now(s["date_format"])))
    for name, text in lines:
        size = s[name + "_size"]
        xy = (SIZE / 2 + s[name + "_x"], SIZE / 2 + s[name + "_y"])
        draw.text(xy, text, fill=s["text_color"], font=get_font(s["font"], size), anchor="mm",
                  stroke_width=max(1, size // 25) if s["outline"] else 0, stroke_fill="black")
    return image


# ---------- bot (runs in a background thread) ----------

def report(text, state="busy"):
    """state: idle | busy | live | error - colors the status dot."""
    print(text)
    messages.put(("status", text, state))


def wait_for(browser, selectors):
    """Wait until every selector matches something; False if stopped."""
    while not stop_event.is_set():
        missing = [name for name, sel in selectors.items() if not browser.find_elements(By.CSS_SELECTOR, sel)]
        if not missing:
            return True
        report("Waiting for: " + ", ".join(missing))
        stop_event.wait(3)
    return False


# runs in every page before the page's own scripts, so navigator.webdriver reads false
HIDE_WEBDRIVER = """() => {
    Object.defineProperty(Navigator.prototype, "webdriver", {get: () => false, configurable: true});
}"""


def wait_for_login(browser, file_input):
    """Wait for the profile page; if the login form is still there after a while, press its button."""
    started = time.time()
    clicked = False
    while not stop_event.is_set():
        if browser.find_elements(By.CSS_SELECTOR, file_input):
            return True
        buttons = browser.find_elements(By.CSS_SELECTOR, 'div[role="button"]')
        if not clicked and time.time() - started > 8 and buttons and browser.find_elements(By.CSS_SELECTOR, 'input[name="pass"]'):
            # a JavaScript click goes through even when another element covers the button
            browser.execute_script("arguments[0].click();", buttons[0])
            clicked = True
        report("Waiting for the profile page...")
        stop_event.wait(3)
    return False


def bot(username, password, headless):
    browser = None
    failed = False
    try:
        options = Options()
        if headless:
            options.add_argument("--headless")
        options.enable_bidi = True  # needed for the preload script below
        report("Opening browser...")
        browser = webdriver.Firefox(options=options)
        browser.script.add_preload_script(HIDE_WEBDRIVER)
        browser.get("https://www.instagram.com/accounts/edit")
        selectors = {
            "email": 'input[name="email"]',
            "pass": 'input[name="pass"]',
        }
        if not wait_for(browser, selectors):
            return
        stop_event.wait(2)  # let the page finish loading
        report("Logging in...")
        browser.find_element(By.CSS_SELECTOR, selectors["email"]).send_keys(username)
        # Enter submits the form without a click, so overlays (cookie banner, loading screen) can't block it
        browser.find_element(By.CSS_SELECTOR, selectors["pass"]).send_keys(password, Keys.RETURN)

        file_input = {"file": 'input[type="file"]'}
        if not wait_for_login(browser, file_input["file"]):
            return
        report("Logged in", "live")
        count = 0
        while not stop_event.is_set():
            with lock:
                s = dict(settings)
            render(s, new_pick(s, count)).save(PICTURE_FILE)
            if not wait_for(browser, file_input):
                return
            browser.find_element(By.CSS_SELECTOR, file_input["file"]).send_keys(PICTURE_FILE)
            count += 1
            interval = max(15, s["interval"])
            report("Picture changed at %s" % time.strftime("%H:%M:%S"), "live")
            messages.put(("upload", count, time.time() + interval))
            stop_event.wait(interval)
    except Exception as e:
        failed = True
        message = getattr(e, "msg", None) or str(e)  # selenium's msg leaves out the long stacktrace
        if browser and not headless:
            report("Error: %s\n\nThe browser stays open so you can see what happened. Press Stop to close it." % message, "error")
            stop_event.wait()
        else:
            report("Error: %s" % message, "error")
    finally:
        if browser:
            browser.quit()
        if not failed:
            report("Stopped", "idle")
        messages.put(("done",))


# ---------- GUI ----------

BG = "#0e0e13"
SIDEBAR = "#14141b"
CARD = "#1a1a23"
FIELD = "#24242f"
BORDER = "#2c2c3a"
MUTED = "#8b8ba3"
ACCENT = "#e1306c"
ACCENT_HOVER = "#c2255c"
STATE_COLORS = {"idle": MUTED, "busy": "#f5a524", "live": "#22c55e", "error": "#ef4444"}
PREVIEW = 300

settings = load_settings()
lock = threading.Lock()
stop_event = threading.Event()
messages = queue.Queue()
worker = None
running = False
next_upload = None

ctk.set_appearance_mode("dark")
window = ctk.CTk(fg_color=BG)
window.title("Clock Bot")
window.geometry("1240x780")
window.minsize(1180, 740)
window.grid_columnconfigure(1, weight=1)
window.grid_rowconfigure(0, weight=1)

variables = {}
color_buttons = {}
hooks = {}  # key -> function called after that setting changes
ready = False  # widgets write to their vars while being built


def font(size, weight="normal"):
    return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)


def set_setting(key, value):
    with lock:
        settings[key] = value
    if key in hooks:
        hooks[key]()
    if ready:
        update_preview()


def bind(key, var):
    var.set(settings[key])
    variables[key] = var

    def changed(*_):
        try:
            value = var.get()
        except TclError:
            return
        set_setting(key, value)

    var.trace_add("write", changed)
    return var


def card(parent, title=None, expand=False):
    frame = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=16, border_width=1, border_color=BORDER)
    frame.pack(fill="both" if expand else "x", expand=expand, pady=(0, 12))
    if title:
        ctk.CTkLabel(frame, text=title.upper(), font=font(11, "bold"), text_color=MUTED, height=20).pack(anchor="w", padx=18, pady=(14, 6))
    body = ctk.CTkFrame(frame, fg_color="transparent")
    body.pack(fill="both", expand=expand, padx=18, pady=(0 if title else 14, 16))
    return body


def label(parent, text, size=13, color=None, weight="normal", **kwargs):
    return ctk.CTkLabel(parent, text=text, font=font(size, weight), text_color=color, **kwargs)


def secondary_button(parent, text, command, **kwargs):
    return ctk.CTkButton(parent, text=text, command=command, font=font(13, "bold"), fg_color=FIELD, hover_color=BORDER,
                         corner_radius=10, height=34, **kwargs)


def slider(parent, text, key, low, high, suffix=""):
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", pady=4)
    label(row, text, width=80, anchor="w").pack(side="left")
    value = label(row, "%d%s" % (settings[key], suffix), weight="bold", width=52, anchor="e")
    value.pack(side="right")

    def moved(v):
        v = int(round(v))
        value.configure(text="%d%s" % (v, suffix))
        set_setting(key, v)

    widget = ctk.CTkSlider(row, from_=low, to=high, number_of_steps=high - low, command=moved, height=18,
                           progress_color=ACCENT, button_color="white", button_hover_color="#f1f1f1", fg_color=FIELD)
    widget.set(settings[key])
    widget.pack(side="left", fill="x", expand=True, padx=10)


def switch(parent, text, key=None, variable=None, command=None):
    var = variable or BooleanVar(value=settings[key])

    def toggled():
        if key:
            set_setting(key, var.get())
        if command:
            command()

    widget = ctk.CTkSwitch(parent, text=text, variable=var, onvalue=True, offvalue=False, command=toggled, font=font(13),
                           progress_color=ACCENT, button_color="white", button_hover_color="#f1f1f1", fg_color=FIELD)
    widget.pack(anchor="w", pady=4)
    return widget


def segmented(parent, key, options, **kwargs):
    """Segmented control for settings[key]; options are (label, value) pairs."""
    to_value = dict(options)
    to_label = {v: l for l, v in options}
    current = settings[key]
    if current not in to_label:  # e.g. an interval that is no longer offered
        current = min(to_label, key=lambda v: abs(v - current)) if isinstance(current, (int, float)) else options[0][1]
        settings[key] = current
    widget = ctk.CTkSegmentedButton(parent, values=[l for l, _ in options], command=lambda l: set_setting(key, to_value[l]),
                                    font=font(13, "bold"), height=34, corner_radius=10, fg_color=FIELD,
                                    selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
                                    unselected_color=FIELD, unselected_hover_color=BORDER, **kwargs)
    widget.set(to_label[current])
    widget.choose = lambda value: (widget.set(to_label[value]), set_setting(key, value))
    return widget


def readable_on(color):
    r, g, b = ImageColor.getrgb(color)[:3]
    return "black" if r * 0.299 + g * 0.587 + b * 0.114 > 150 else "white"


def color_button(parent, key):
    button = ctk.CTkButton(parent, text=settings[key].upper(), width=100, height=34, corner_radius=10, font=font(12, "bold"),
                           border_width=2, border_color=BORDER)

    def choose():
        color = colorchooser.askcolor(settings[key], parent=window)[1]
        if color:
            set_color(key, color)

    button.configure(command=choose)
    color_buttons[key] = button
    paint_color_button(key)
    return button


def paint_color_button(key):
    color = settings[key]
    color_buttons[key].configure(text=color.upper(), fg_color=color, hover_color=color, text_color=readable_on(color))


def set_color(key, color):
    set_setting(key, color)
    paint_color_button(key)


def rounded(image, radius):
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, image.width - 1, image.height - 1), radius=radius, fill=255)
    out = Image.new("RGBA", image.size, (0, 0, 0, 0))
    out.paste(image, (0, 0), mask)
    return out


def make_logo(size=176):
    logo = rounded(multi_gradient(INSTAGRAM, size, 45), size // 4)
    draw = ImageDraw.Draw(logo)
    c, r, w = size / 2, size * 0.27, max(2, size // 16)
    draw.ellipse((c - r, c - r, c + r, c + r), outline="white", width=w)
    draw.line((c, c, c, c - r * 0.6), fill="white", width=w)
    draw.line((c, c, c + r * 0.45, c), fill="white", width=w)
    return logo


# --- left sidebar: brand, account, run ---
sidebar = ctk.CTkFrame(window, fg_color=SIDEBAR, corner_radius=0, width=320)
sidebar.grid(row=0, column=0, sticky="nsew")
sidebar.grid_propagate(False)
side = ctk.CTkFrame(sidebar, fg_color="transparent")
side.pack(fill="both", expand=True, padx=20, pady=22)

logo = make_logo()
brand = ctk.CTkFrame(side, fg_color="transparent")
brand.pack(fill="x", pady=(0, 22))
ctk.CTkLabel(brand, text="", image=ctk.CTkImage(logo, logo, size=(46, 46))).pack(side="left")
brand_text = ctk.CTkFrame(brand, fg_color="transparent")
brand_text.pack(side="left", padx=12)
label(brand_text, "Clock Bot", 22, weight="bold", height=28).pack(anchor="w")
label(brand_text, "Live clock profile picture", 12, MUTED, height=16).pack(anchor="w")

account = card(side, "Account")
username = StringVar()
username_entry = ctk.CTkEntry(account, textvariable=username, placeholder_text="Username or email", height=40, corner_radius=10,
                              font=font(14), fg_color=FIELD, border_color=BORDER)
username_entry.pack(fill="x", pady=(0, 8))
password_entry = ctk.CTkEntry(account, placeholder_text="Password", show="•", height=40, corner_radius=10,
                              font=font(14), fg_color=FIELD, border_color=BORDER)
password_entry.pack(fill="x", pady=(0, 6))
show_browser = BooleanVar(value=True)
switch(account, "Show browser window", variable=show_browser)

schedule = card(side, "Update every")
segmented(schedule, "interval", (("15s", 15), ("30s", 30), ("1m", 60), ("2m", 120), ("5m", 300), ("10m", 600))).pack(fill="x")

start_button = ctk.CTkButton(side, text="Start", height=50, corner_radius=14, font=font(17, "bold"),
                             fg_color=ACCENT, hover_color=ACCENT_HOVER)
start_button.pack(fill="x", pady=(4, 14))

status_body = card(side)
status_row = ctk.CTkFrame(status_body, fg_color="transparent")
status_row.pack(fill="x")
status_dot = label(status_row, "●", 16, MUTED, width=18)
status_dot.pack(side="left")
status_title = label(status_row, "Ready", 14, weight="bold")
status_title.pack(side="left", padx=6)
status_text = label(status_body, "Sign in and press Start.", 12, MUTED, wraplength=250, justify="left", anchor="w")
status_text.pack(fill="x", pady=(2, 10))
stats = ctk.CTkFrame(status_body, fg_color="transparent")
stats.pack(fill="x")
stats.grid_columnconfigure((0, 1), weight=1)
stat_values = {}
for column, (key, title) in enumerate((("uploads", "Uploads"), ("next", "Next update"))):
    box = ctk.CTkFrame(stats, fg_color=FIELD, corner_radius=12)
    box.grid(row=0, column=column, sticky="ew", padx=(0, 6) if column == 0 else (6, 0))
    stat_values[key] = label(box, "0" if key == "uploads" else "--", 20, weight="bold", height=26)
    stat_values[key].pack(anchor="w", padx=12, pady=(10, 0))
    label(box, title, 11, MUTED, height=16).pack(anchor="w", padx=12, pady=(0, 10))

# --- middle: design tabs ---
tabs = ctk.CTkTabview(window, fg_color=BG, corner_radius=16, segmented_button_fg_color=FIELD,
                      segmented_button_selected_color=ACCENT, segmented_button_selected_hover_color=ACCENT_HOVER,
                      segmented_button_unselected_color=FIELD, segmented_button_unselected_hover_color=BORDER,
                      anchor="w")
tabs.grid(row=0, column=1, sticky="nsew", padx=(20, 10), pady=(8, 20))
tabs._segmented_button.configure(font=font(14, "bold"), height=36)
background_tab = tabs.add("Background")
text_tab = tabs.add("Text")

# background type + its options
type_body = card(background_tab, "Background")
MODES = (("Random", "random"), ("Color", "color"), ("Gradient", "gradient"), ("Daytime", "daytime"), ("Images", "image"))
mode_switch = segmented(type_body, "background_mode", MODES)
mode_switch.pack(fill="x", pady=(0, 14))
panel_host = ctk.CTkFrame(type_body, fg_color="transparent")
panel_host.pack(fill="x")
panels = {mode: ctk.CTkFrame(panel_host, fg_color="transparent") for _, mode in MODES}

# random
label(panels["random"], "A fresh color from this palette on every update.", 12, MUTED).pack(anchor="w")
swatches = ctk.CTkFrame(panels["random"], fg_color="transparent")
swatches.pack(anchor="w", pady=(6, 0))
for i, color in enumerate(COLORS):
    ctk.CTkFrame(swatches, width=30, height=30, corner_radius=9, fg_color=color).grid(row=0, column=i, padx=(0, 6))

# single color
color_row = ctk.CTkFrame(panels["color"], fg_color="transparent")
color_row.pack(anchor="w")
label(color_row, "Color", width=80, anchor="w").pack(side="left")
color_button(color_row, "background_color").pack(side="left")

# gradient
gradient_row = ctk.CTkFrame(panels["gradient"], fg_color="transparent")
gradient_row.pack(fill="x", pady=(0, 8))
label(gradient_row, "Colors", width=80, anchor="w").pack(side="left")
color_button(gradient_row, "gradient_color1").pack(side="left")
label(gradient_row, "→", 16, MUTED, width=30).pack(side="left")
color_button(gradient_row, "gradient_color2").pack(side="left")


def swap_gradient():
    c1, c2 = settings["gradient_color1"], settings["gradient_color2"]
    set_color("gradient_color1", c2)
    set_color("gradient_color2", c1)


secondary_button(gradient_row, "⇄  Swap", swap_gradient, width=80).pack(side="left", padx=(10, 0))
style_row = ctk.CTkFrame(panels["gradient"], fg_color="transparent")
style_row.pack(fill="x", pady=(0, 4))
label(style_row, "Style", width=80, anchor="w").pack(side="left")
segmented(style_row, "gradient_style", (("Linear", "linear"), ("Radial", "radial")), width=200).pack(side="left")
slider(panels["gradient"], "Angle", "gradient_angle", 0, 359, "°")
switch(panels["gradient"], "Random palette pair on every update", "gradient_random")

# daytime: the whole day's sky as a strip
label(panels["daytime"], "A sky that follows the clock — night, sunrise, day, sunset.", 12, MUTED).pack(anchor="w")
strip = Image.new("RGB", (480, 40))
for x in range(strip.width):
    top, bottom = daytime_colors(x / 20)
    strip.paste(gradient(top, bottom, "linear", 0).resize((1, strip.height)), (x, 0))
strip = rounded(strip, 10)
ctk.CTkLabel(panels["daytime"], text="", image=ctk.CTkImage(strip, strip, size=(480, 40))).pack(anchor="w", pady=(8, 2))
hours = ctk.CTkFrame(panels["daytime"], fg_color="transparent", width=480, height=18)
hours.pack(anchor="w")
for i, text in enumerate(("00:00", "06:00", "12:00", "18:00", "24:00")):
    label(hours, text, 11, MUTED, height=18).place(relx=i / 4, x=-16 if 0 < i < 4 else (0 if i == 0 else -34), y=0)

# images
image_rows = ctk.CTkScrollableFrame(panels["image"], height=120, fg_color=FIELD, corner_radius=12,
                                    scrollbar_button_color=BORDER, scrollbar_button_hover_color=MUTED)
image_rows.pack(fill="x", pady=(0, 8))
image_actions = ctk.CTkFrame(panels["image"], fg_color="transparent")
image_actions.pack(fill="x", pady=(0, 10))
order_row = ctk.CTkFrame(panels["image"], fg_color="transparent")
order_row.pack(fill="x", pady=(0, 8))
label(order_row, "Order", width=80, anchor="w").pack(side="left")
segmented(order_row, "image_order", (("Shuffle", "random"), ("In order", "order")), width=200).pack(side="left")
fit_row = ctk.CTkFrame(panels["image"], fg_color="transparent")
fit_row.pack(fill="x")
label(fit_row, "Fit", width=80, anchor="w").pack(side="left")
segmented(fit_row, "image_fit", (("Fill", "fill"), ("Whole image", "fit")), width=200).pack(side="left")
thumbnails = {}


def refresh_image_list():
    for widget in image_rows.winfo_children():
        widget.destroy()
    if not settings["background_images"]:
        label(image_rows, "No images yet — add a few to rotate through.", 12, MUTED).pack(pady=40)
    for path in settings["background_images"]:
        row = ctk.CTkFrame(image_rows, fg_color=CARD, corner_radius=10)
        row.pack(fill="x", pady=3, padx=2)
        try:
            thumb = rounded(background_image(path, "fill").resize((72, 72)), 14)
            thumbnails[path] = ctk.CTkImage(thumb, thumb, size=(36, 36))
        except OSError:
            thumbnails[path] = None
        ctk.CTkLabel(row, text="" if thumbnails[path] else "?", image=thumbnails[path], width=36).pack(side="left", padx=8, pady=6)
        label(row, os.path.basename(path), 12, anchor="w").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="✕", width=30, height=30, corner_radius=8, fg_color="transparent", hover_color=BORDER,
                      font=font(13), command=lambda p=path: remove_image(p)).pack(side="right", padx=6)


def add_images():
    paths = filedialog.askopenfilenames(parent=window, title="Background images",
                                        filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif")])
    if not paths:
        return
    with lock:
        settings["background_images"] = settings["background_images"] + [p for p in paths if p not in settings["background_images"]]
    refresh_image_list()
    mode_switch.choose("image")
    shuffle()


def remove_image(path):
    with lock:
        settings["background_images"] = [p for p in settings["background_images"] if p != path]
    refresh_image_list()
    shuffle()


def clear_images():
    with lock:
        settings["background_images"] = []
    refresh_image_list()
    shuffle()


ctk.CTkButton(image_actions, text="＋  Add images", command=add_images, font=font(13, "bold"), height=34, corner_radius=10,
              fg_color=ACCENT, hover_color=ACCENT_HOVER).pack(side="left")
secondary_button(image_actions, "Clear all", clear_images, width=90).pack(side="left", padx=8)
refresh_image_list()


def show_panel():
    for mode, panel in panels.items():
        if mode == settings["background_mode"]:
            panel.pack(fill="x")
        else:
            panel.pack_forget()


hooks["background_mode"] = show_panel
show_panel()

effects = card(background_tab, "Effects")
slider(effects, "Darken", "darken", 0, 90, "%")
slider(effects, "Blur", "blur", 0, 20)
slider(effects, "Vignette", "vignette", 0, 100, "%")
switch(effects, "Black & white", "grayscale")

# text tab
style_body = card(text_tab, "Style")
text_color_row = ctk.CTkFrame(style_body, fg_color="transparent")
text_color_row.pack(fill="x", pady=(0, 8))
label(text_color_row, "Color", width=80, anchor="w").pack(side="left")
color_button(text_color_row, "text_color").pack(side="left")
font_row = ctk.CTkFrame(style_body, fg_color="transparent")
font_row.pack(fill="x", pady=(0, 4))
label(font_row, "Font", width=80, anchor="w").pack(side="left")
font_name = label(font_row, os.path.basename(settings["font"]), weight="bold")
font_name.pack(side="left")


def choose_font():
    path = filedialog.askopenfilename(parent=window, title="Font", initialdir=os.path.dirname(settings["font"]),
                                      filetypes=[("Fonts", "*.ttf *.otf *.TTF *.OTF")])
    if path:
        font_name.configure(text=os.path.basename(path))
        set_setting("font", path)


secondary_button(font_row, "Choose…", choose_font, width=90).pack(side="left", padx=12)
switch(style_body, "Black outline", "outline")


def text_card(title, prefix, toggle=None):
    body = card(text_tab, title)
    top = ctk.CTkFrame(body, fg_color="transparent")
    top.pack(fill="x", pady=(0, 4))
    label(top, "Format", width=80, anchor="w").pack(side="left")
    ctk.CTkEntry(top, textvariable=bind(prefix + "_format", StringVar()), width=150, height=34, corner_radius=10,
                 font=font(13), fg_color=FIELD, border_color=BORDER).pack(side="left")
    if toggle:
        ctk.CTkSwitch(top, text="Show", variable=bind(toggle, BooleanVar()), onvalue=True, offvalue=False, font=font(13),
                      progress_color=ACCENT, button_color="white", button_hover_color="#f1f1f1", fg_color=FIELD).pack(side="right")
    slider(body, "Size", prefix + "_size", 10, 200)
    slider(body, "X", prefix + "_x", -SIZE // 2, SIZE // 2)
    slider(body, "Y", prefix + "_y", -SIZE // 2, SIZE // 2)


text_card("Time", "time")
text_card("Date", "date", toggle="date_show")
label(text_tab, "Formats:  %H:%M  ·  %I:%M %p  ·  %d-%b-%y  ·  %A, %d %B", 12, MUTED).pack(anchor="w", padx=4)

# --- right: live preview ---
right = ctk.CTkFrame(window, fg_color="transparent", width=360)
right.grid(row=0, column=2, sticky="ns", padx=(10, 20), pady=20)
preview_body = card(right, "Live preview", expand=True)
preview = ctk.CTkLabel(preview_body, text="")
preview.pack(pady=(6, 10))
preview_name = label(preview_body, "@username", 16, weight="bold", height=22)
preview_name.pack()
label(preview_body, "Updates every second", 12, MUTED, height=18).pack(pady=(0, 16))
view_mode = StringVar(value="Profile")
ctk.CTkSegmentedButton(preview_body, values=["Profile", "Square"], variable=view_mode, command=lambda _: update_preview(),
                       font=font(13, "bold"), height=34, corner_radius=10, fg_color=FIELD, selected_color=ACCENT,
                       selected_hover_color=ACCENT_HOVER, unselected_color=FIELD, unselected_hover_color=BORDER).pack(fill="x", pady=(0, 8))
preview_pick = None


def shuffle():
    """Pick new random colors/image for the preview."""
    global preview_pick
    with lock:
        preview_pick = new_pick(settings)
    update_preview()


secondary_button(preview_body, "🎲  Shuffle", shuffle).pack(fill="x")


@lru_cache(maxsize=1)
def profile_frame():
    """Instagram-style ring around the avatar, drawn at 2x for smooth edges."""
    s = PREVIEW * 2
    frame = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ring_mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(ring_mask).ellipse((0, 0, s - 1, s - 1), fill=255)
    frame.paste(multi_gradient(INSTAGRAM, s, 45), (0, 0), ring_mask)
    gap = round(s * 0.03)
    ImageDraw.Draw(frame).ellipse((gap, gap, s - 1 - gap, s - 1 - gap), fill=CARD)
    inset = round(s * 0.065)
    avatar_mask = Image.new("L", (s - 2 * inset, s - 2 * inset), 0)
    ImageDraw.Draw(avatar_mask).ellipse((0, 0, avatar_mask.width - 1, avatar_mask.height - 1), fill=255)
    return frame, inset, avatar_mask


def update_preview():
    with lock:
        s = dict(settings)
    image = render(s, preview_pick)
    if view_mode.get() == "Profile":
        frame, inset, avatar_mask = profile_frame()
        shown = frame.copy()
        shown.paste(image.resize(avatar_mask.size, Image.LANCZOS), (inset, inset), avatar_mask)
    else:
        shown = rounded(image.resize((PREVIEW * 2, PREVIEW * 2), Image.LANCZOS), 36)
    photo = ctk.CTkImage(shown, shown, size=(PREVIEW, PREVIEW))
    preview.configure(image=photo)
    preview.image = photo


def update_name(*_):
    preview_name.configure(text="@" + (username.get().strip() or "username"))


username.trace_add("write", update_name)


# --- running the bot ---

def set_status(title, text, state):
    status_dot.configure(text_color=STATE_COLORS[state])
    status_title.configure(text=title)
    status_text.configure(text=text)


STATE_TITLES = {"idle": "Ready", "busy": "Working", "live": "Live", "error": "Error"}


def tick():
    update_preview()
    if running and next_upload:
        stat_values["next"].configure(text="%ds" % max(0, round(next_upload - time.time())))
    window.after(1000, tick)


def check_messages():
    global running, next_upload
    while True:
        try:
            message = messages.get_nowait()
        except queue.Empty:
            break
        if message[0] == "status":
            _, text, state = message
            set_status(STATE_TITLES[state], text, state)
        elif message[0] == "upload":
            _, count, next_upload = message
            stat_values["uploads"].configure(text=str(count))
        elif message[0] == "done":
            running = False
            next_upload = None
            stat_values["next"].configure(text="--")
            start_button.configure(text="Start", state="normal", fg_color=ACCENT, hover_color=ACCENT_HOVER)
    window.after(200, check_messages)


def start_or_stop():
    global worker, running
    if running:
        stop_event.set()
        set_status("Stopping", "Closing the browser…", "busy")
        start_button.configure(text="Stopping…", state="disabled")
        return
    if not username.get() or not password_entry.get():
        set_status("Missing login", "Enter your username and password first.", "error")
        return
    save_settings()
    stop_event.clear()
    running = True
    stat_values["uploads"].configure(text="0")
    worker = threading.Thread(target=bot, args=(username.get(), password_entry.get(), not show_browser.get()))
    worker.start()
    start_button.configure(text="Stop", fg_color=FIELD, hover_color=BORDER)


def on_close():
    save_settings()
    stop_event.set()  # the bot thread closes Firefox before the process exits
    window.destroy()


start_button.configure(command=start_or_stop)
window.protocol("WM_DELETE_WINDOW", on_close)
# customtkinter sets its own window icon shortly after start, so set ours after it
icon = ImageTk.PhotoImage(logo.resize((64, 64), Image.LANCZOS))
window.after(300, lambda: window.iconphoto(True, icon))
ready = True
shuffle()
tick()
check_messages()
window.mainloop()
