# Skywatch

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
  (default 70 km).

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
