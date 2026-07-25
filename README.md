# Skywatch

**Made by love in Norway 🇳🇴**

A small web page that shows the last aircraft your ADS-B antenna picked up.
When there's an active connection it shows flight number, airline, logo,
altitude, speed and distance. When there's no active connection it shows the
last flight seen, its route, and an estimate of when it landed based on last
known position/speed and distance to the destination (not real schedule
data — see "Limitations" below).

## Data source

`readsb-install.sh` from wiedehopf/adsb-scripts installs tar1090
automatically as part of the install. The webinterface is therefore at
`http://<ip>/tar1090`, and aircraft.json at
`http://<ip>/tar1090/data/aircraft.json`.

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
- `REGION_TEXT` — the region name shown on screen, e.g. "Østlandet". Pick
  something that roughly matches your actual `MAX_RANGE_KM` coverage area,
  not just your city - a wide-range antenna will pick up aircraft well
  outside your immediate local area.
- `ANTENNA_LOCATION_TEXT` — where your antenna actually is, shown on screen
  as e.g. "ADS-B-antenne er plassert i <this>."

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
chromium-browser --noerrdialogs --disable-infobars --kiosk http://skywatch.grandedata.no
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

