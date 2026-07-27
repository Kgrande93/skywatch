# Skywatch

**Made by love in Nannestad, Norway 🇳🇴**

A small web page that shows the last aircraft your ADS-B antenna picked up.
When there's an active connection it shows flight number, airline, logo,
altitude, speed and distance. When there's no active connection it shows the
last flight seen, its route, and an estimate of when it landed based on last
known position/speed and distance to the destination (not real schedule
data — see "Limitations" below).

**Prerequisite**: this needs an ADS-B receiver already feeding readsb/tar1090
somewhere on your network. If you don't have that running yet, see
[github.com/Kgrande93/FR24Feed](https://github.com/Kgrande93/FR24Feed) for a
full setup guide (RTL2832U dongle + readsb + tar1090 + FlightRadar24 feeding
on a Debian VM).

## Two view modes

Skywatch has two separate pages, sharing the same live data:

- **`/`** — desktop view. Denser layout with more detail (full airport
  names, all metrics), meant for a normal screen viewed up close. Click the
  ‹ › arrows or the dots to jump to a specific aircraft manually — automatic
  rotation keeps running in the background and picks up from wherever you
  left it.
- **`/kiosk`** — dense, FlightWall-inspired layout with larger text and
  simplified content (airport codes only, no full names), designed to be
  legible from a few meters away on a small always-on display. See
  "Running it on a screen" below for the physical setup this is built for.

## Data source

`readsb-install.sh` from wiedehopf/adsb-scripts installs tar1090
automatically as part of the install. The webinterface is therefore at
`http://<ip>/tar1090`, and aircraft.json at
`http://<ip>/tar1090/data/aircraft.json`.

**Finding `<ip>`**: it's whatever machine is running readsb/tar1090 - for
example the VM from the [FR24Feed](https://github.com/Kgrande93/FR24Feed)
setup. Find its IP from your router's client list, or by running
`hostname -I` directly on that machine over SSH.

**Test the URL before configuring Skywatch** - open
`http://<that-ip>/tar1090` in a browser and confirm you see the live map, or
check that this returns real JSON (not empty/404):

```bash
curl -s http://<that-ip>/tar1090/data/aircraft.json | head -c 200
```

If this doesn't work, Skywatch won't have any data to show either -
troubleshoot readsb/tar1090 first before touching Skywatch's own config.

`skywatch.service` (the filled-in version with your real values) is in
`.gitignore` and is never tracked — only `skywatch.service.example` with
placeholders lives in the repo. On the host, copy the example and fill in
your own values:

```bash
cp skywatch.service.example skywatch.service
nano skywatch.service   # fill in AIRCRAFT_JSON_URL, RECEIVER_LAT, RECEIVER_LON
```

`app.py`'s defaults for `RECEIVER_LAT`/`RECEIVER_LON` are `0`, and the app
logs a clear warning on startup if they haven't been set.

## Other things you need to set

- `RECEIVER_LAT` / `RECEIVER_LON` — your antenna's position (used for
  distance, and for picking the "closest aircraft" when several are in
  range). The code has no real default here — set your actual coordinates.
- `MAX_RANGE_KM` — how far away an aircraft still counts as "in range"
  (default 70 km). Note this can genuinely be 200-300+ km for a decent
  antenna with clear line of sight - check the range-discovery log below
  before assuming a low default is correct.
- `REGION_TEXT` — the region name shown on screen, e.g. "Gardermoen area".
  Pick something that roughly matches your actual `MAX_RANGE_KM` coverage
  area, not just your city - a wide-range antenna will pick up aircraft
  well outside your immediate local area.
- `ANTENNA_LOCATION_TEXT` — where your antenna actually is, shown on screen
  as e.g. "ADS-B antenna is located in <this>."
- `TIMEZONE` — an IANA timezone name (e.g. `Europe/Oslo`), default
  `Europe/Oslo`. Used for date/time-based features (holiday effects etc.) so
  they trigger at the right local moment regardless of what timezone the
  host machine's system clock happens to be set to.

> Both of these are free text and often contain spaces/commas - the
> `.example` file already wraps them in quotes
> (`Environment="REGION_TEXT=..."`). If you ever rewrite these lines by
> hand, keep the quotes around the whole `KEY=value` pair, not just the
> value - systemd otherwise silently truncates at the first space.

## Installation (new LXC, Debian)

```bash
sudo apt update && sudo apt install -y python3-venv git
sudo useradd -r -s /usr/sbin/nologin skywatch
sudo mkdir -p /opt/skywatch /var/lib/skywatch
sudo chown skywatch:skywatch /var/lib/skywatch

git clone https://github.com/Kgrande93/skywatch.git /opt/skywatch
sudo chown -R skywatch:skywatch /opt/skywatch

cd /opt/skywatch
sudo -u skywatch python3 -m venv venv
sudo -u skywatch venv/bin/pip install -r requirements.txt

cp skywatch.service.example skywatch.service
nano skywatch.service   # fill in your own values, see above

sudo cp skywatch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now skywatch
```

The page then answers on `http://<host-ip>:5000`. Put it behind a reverse
proxy as a new host, same as your other services.

## Airline logos

Logos are fetched from AirHex (`content.airhex.com`) on their free/demo
tier without an API key — works, but may carry a small watermark. If you
have a free AirHex API key, set `AIRHEX_APIKEY` as an environment variable
and the URL automatically switches to the signed, watermark-free variant.

## Finding your antenna's real range

Every aircraft's farthest-seen distance (regardless of `MAX_RANGE_KM`) is
logged to `/var/lib/skywatch/distance_log.jsonl` - one line per new
distance record for that aircraft. Check it any time with:

```bash
curl -s http://127.0.0.1:5000/api/range-log | python3 -m json.tool
```

This shows every aircraft sorted farthest-first, so you can see your
antenna's actual range and tune `MAX_RANGE_KM` to match reality instead of
guessing.

## 🎅 Easter egg: Santa, snow, and fireworks

A few seasonal extras run automatically, all based on the `TIMEZONE` setting
(not the host machine's system clock) - no manual switch needed.

**Snow** - a light, subtle snowflake layer falls over the whole screen from
the 1st Sunday of Advent (calculated per year - the 4th Sunday before Dec 25)
through December 30th. Purely decorative, low opacity, doesn't interfere with
reading the flight data.

**Santa's sleigh** - from Dec 24 evening through Dec 25, `SANTA01` (Santa
Airlines, aircraft type "Sleigh") joins the normal aircraft rotation as one
more tracked "flight," alongside any real aircraft in range. His route,
speed, altitude, and position are computed live:

- `santa_route.py` lists ~60 countries (a representative global sample, not
  all ~195 - easy to extend in the same format), each with its own timezone
  and the local clock time its actual Christmas gift-giving tradition calls
  for: evening of Dec 24 for most of Europe, midnight for most of Latin
  America, morning of Dec 25 for the Anglophone world. Countries where a
  different figure delivers gifts on a different date entirely (Netherlands/
  Belgium: Sinterklaas Dec 5-6, Spain: Three Kings Jan 6, Russia and several
  Orthodox countries: New Year/Jan 7) are deliberately left out of the route.
- Each country's local arrival time is converted to UTC and the whole list
  is sorted chronologically, bookended by two virtual "North Pole" stops -
  this is what actually decides the order Santa visits countries in, which
  doesn't stay neatly east-to-west since evening-24 and morning-25 countries
  interleave.
- Between two stops, position is interpolated along a great-circle path,
  speed = leg distance ÷ leg duration, and altitude follows a climb
  (first 15% of the leg) → cruise at a deliberately absurd 241,200 ft →
  descend (last 15%) profile, the same shape a real flight's altitude
  graph would have, just compressed.

**Fireworks** - a quiet background layer of firework bursts appears for 5
minutes starting at 00:00 on January 1st, local time. It sits behind the
normal flight display rather than replacing it.

**Testing without waiting for the actual date**: temporarily set the system
clock forward **on the machine running Skywatch itself** (not the FR24Feed
VM - that clock is irrelevant here), e.g.:

```bash
sudo date -s "2026-12-24 16:55:00"
```

Remember to set it back afterward (`sudo systemctl restart systemd-timesyncd`
or `sudo hwclock -s`), since other things on the same host may also depend
on the correct time.

## Limitations

- "Estimated landing" is NOT pulled from a real schedule — it's distance
  (last position → destination airport) divided by last known speed. Good
  enough as a rough indicator, but gets less accurate during approach when
  speed changes a lot. A real ETA would require a paid source like
  FlightAware AeroAPI.
- Flight route/airline comes from ADSBdb (free, no key), which doesn't know
  every callsign — military, private, and some charter flights will be
  missing route/airline info.
- When several aircraft are in range at the same time, the page
  automatically rotates between them every 6 seconds (dots at the bottom
  show how many / which one is showing).

## Running it on a screen (kiosk mode)

The layout is built to fill a whole screen and stay legible from a
distance, so it works well as a dedicated always-on display.

### Hardware

- **Raspberry Pi 3B or newer** — plenty for this (mostly text, one small
  logo image, and a simple CSS animation). Get one with WiFi built in if
  you don't want to run an Ethernet cable.
- **A screen with HDMI input** — for example
  [this one from AliExpress](https://www.aliexpress.com/item/1005010755027785.html).
  Double-check the listing yourself before buying: it needs to be **HDMI**,
  not a DSI ribbon-cable display — those are usually wired specifically for
  official Raspberry Pi touchscreens and won't work the same way with a
  generic setup.

### Flashing the Pi

1. Download **Raspberry Pi Imager** (Mac/Windows/Linux) from
   raspberrypi.com/software
2. Choose OS → **Raspberry Pi OS Lite** (current release is based on
   Debian "Trixie") — no desktop environment needed since Chromium runs in
   kiosk mode directly
3. Choose your SD card as the target
4. Click the gear icon (or `Cmd+Shift+X` / `Ctrl+Shift+X`) for advanced
   options **before** writing:
   - Set a hostname (e.g. `skywatch-display`)
   - Enable SSH (password or your existing public key)
   - Configure WiFi (SSID, password, country) if not using Ethernet
   - Set locale/timezone
5. Save, then write the image. The Pi will join your WiFi automatically on
   first boot — no monitor or keyboard needed to get started.
6. SSH in: `ssh pi@skywatch-display.local` (or use the IP from your router)

### Kiosk mode

```bash
sudo apt update && sudo apt install -y chromium-browser unclutter xserver-xorg x11-xserver-utils xinit openbox
```

Create `~/.config/openbox/autostart` with:

```bash
xset s off
xset -dpms
xset s noblank
unclutter -idle 0.5 -root &
chromium-browser --noerrdialogs --disable-infobars --kiosk http://<your-skywatch-host>/kiosk
```

(swap the URL for wherever your own instance is running)

Auto-start the display on boot by adding to `~/.bash_profile`:

```bash
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
  startx
fi
```

And enable auto-login on tty1 via `sudo raspi-config` → System Options →
Boot / Auto Login → Console Autologin.

