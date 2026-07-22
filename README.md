# Skywatch

Liten webside som viser siste fly antennen din tok imot. Har den en aktiv
forbindelse, vises flynummer, selskap, logo, høyde, fart og avstand. Har den
ingen aktiv forbindelse, vises siste fly med rute og et estimat på når det
landet, basert på siste kjente posisjon/fart og avstand til destinasjonen
(ikke ekte rutetabelldata - se "Begrensninger" under).

## Datakilde

`readsb-install.sh` fra wiedehopf/adsb-scripts installerer tar1090 automatisk
som del av installasjonen. Webgrensesnittet ligger derfor på
`http://<ip>/tar1090`, og aircraft.json på `http://<ip>/tar1090/data/aircraft.json`.

**Ingenting av IP-adresser, posisjon eller annen infrastruktur-info skal
committes til git.** Derfor er `skywatch.service` (den utfylte, ekte
versjonen) i `.gitignore` — bare `skywatch.service.example` med placeholders
ligger i repoet. Kopier den og fyll inn dine egne verdier lokalt på LXC-en:

```bash
cp skywatch.service.example skywatch.service
nano skywatch.service   # fyll inn AIRCRAFT_JSON_URL, RECEIVER_LAT, RECEIVER_LON
```

`app.py` sine standardverdier for `RECEIVER_LAT`/`RECEIVER_LON` er `0`, og
appen logger en tydelig advarsel ved oppstart om de ikke er satt.

## Andre ting du må sette

- `RECEIVER_LAT` / `RECEIVER_LON` - antennens posisjon (brukes til avstand og
  til å velge "nærmeste fly" når flere er innenfor rekkevidde). Placeholder
  i koden er omtrentlig Nannestad-posisjon - bytt ut med faktiske koordinater.
- `MAX_RANGE_KM` - hvor langt unna et fly regnes som "innenfor rekkevidde"
  (standard 70 km).

## Installasjon (ny LXC, Debian)

```
sudo apt update && sudo apt install -y python3-venv
sudo useradd -r -s /usr/sbin/nologin skywatch
sudo mkdir -p /opt/skywatch /var/lib/skywatch
sudo chown skywatch:skywatch /var/lib/skywatch
# kopier app.py, templates/, requirements.txt til /opt/skywatch
cd /opt/skywatch
sudo -u skywatch python3 -m venv venv
sudo -u skywatch venv/bin/pip install -r requirements.txt
sudo cp skywatch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now skywatch
```

Siden svarer da på `http://<lxc-ip>:5000`. Legg den bak NPMplus som en ny
proxy host (samme mønster som resten av tjenestene dine).

## Airline-logo

Logoer hentes fra AirHex (`content.airhex.com`) på deres gratis/demo-nivå
uten API-nøkkel - fungerer, men kan ha et lite vannmerke. Har du en gratis
AirHex API-nøkkel fra før, sett `AIRHEX_APIKEY` som miljøvariabel så byttes
URL-en automatisk til den signerte varianten uten vannmerke.

## Begrensninger

- "Estimert landing" er IKKE hentet fra en ekte rutetabell - det er
  distanse (siste posisjon → destinasjonsflyplass) delt på siste kjente
  fart. Fungerer greit som fingerpek, men blir upresist i innflygingsfasen
  når farten endrer seg mye. En ekte ETA krever en betalt kilde som
  FlightAware AeroAPI.
- Flyrute/selskap kommer fra ADSBdb (gratis, ingen nøkkel), som ikke kjenner
  alle callsign - spesielt militære, private og noen charterflyvninger vil
  mangle rute/selskap.
- Er det flere fly innenfor rekkevidde samtidig, roterer siden automatisk
  mellom dem hvert 6. sekund (prikker nederst viser hvor mange/hvilket).
