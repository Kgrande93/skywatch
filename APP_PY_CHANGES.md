# Endringer i app.py

Seks nye filer legges ved siden av `app.py`: `settings.py`, `admin.py`,
`ntfy_client.py`, `matrix.py`, `geo.py`, samt oppdaterte maler i `templates/`. Dette dokumentet viser nøyaktig hvor i
`app.py` de kobles inn, med eksakt tekst fra den nåværende filen som
ankerpunkt.

## 1. Imports (rundt linje 12-14)

**Finn:**
```python
import requests
from flask import Flask, jsonify, render_template

import santa_route
```

**Erstatt med:**
```python
import requests
from flask import Flask, jsonify, render_template

import santa_route
import settings as settings_module
import ntfy_client
import matrix
from admin import admin_bp
```

## 2. App-oppsett (rundt linje 46)

**Finn:**
```python
app = Flask(__name__)
```

**Erstatt med:**
```python
app = Flask(__name__)
app.secret_key = settings_module.get_or_create_secret_key()
app.register_blueprint(admin_bp)

_settings = settings_module.get_settings()
if _settings.get("ntfy_topic"):
    ntfy_client.start_subscriber(_settings["ntfy_topic"])
```

## 3. Nødsquawk-deteksjon i poll_once (rundt linje 480-489)

**Finn:**
```python
        for ac in sorted(ground_aircraft, key=lambda a: a.get("hex", "")):
            entry = enrich(ac)
            entry["landed"] = True
            entry["landed_at_epoch"] = _ground_since.get(ac.get("hex"), now)
            enriched_list.append(entry)

        _state["active"] = True
        _state["aircraft_list"] = enriched_list
        if closest_enriched:
            _state["last"] = closest_enriched

    save_state_file()
```

**Erstatt med:**
```python
        for ac in sorted(ground_aircraft, key=lambda a: a.get("hex", "")):
            entry = enrich(ac)
            entry["landed"] = True
            entry["landed_at_epoch"] = _ground_since.get(ac.get("hex"), now)
            enriched_list.append(entry)

        _state["active"] = True
        _state["aircraft_list"] = enriched_list
        if closest_enriched:
            _state["last"] = closest_enriched

    for entry in enriched_list:
        check_emergency_squawk(entry)

    save_state_file()
```

**Og legg til denne nye funksjonen rett før `def poll_once():`** (bruker et
nytt globalt sett øverst i filen sammen med de andre modul-nivå settene som
`_ground_since` osv.):

```python
_emergency_alerted = set()  # hex codes we've already sent an ntfy alert for

EMERGENCY_SQUAWKS = {"7500": "HIJACK", "7600": "RADIO FAILURE", "7700": "GENERAL EMERGENCY"}


def check_emergency_squawk(entry):
    """Fires an ntfy alert the first time a given aircraft (by hex) is seen
    squawking an emergency code - not on every poll while it stays active,
    and resets once the squawk clears so a later, separate emergency from
    the same aircraft still alerts."""
    hexid = entry.get("hex")
    squawk = entry.get("squawk")
    settings = settings_module.get_settings()

    if squawk in EMERGENCY_SQUAWKS:
        if hexid and hexid not in _emergency_alerted:
            _emergency_alerted.add(hexid)
            if settings.get("ntfy_emergency_squawk_enabled") and settings.get("ntfy_topic"):
                label = EMERGENCY_SQUAWKS[squawk]
                callsign = entry.get("callsign") or hexid
                ntfy_client.send_message(
                    settings["ntfy_topic"],
                    title=f"Emergency squawk {squawk}",
                    message=f"{callsign} is squawking {squawk} ({label})",
                )
    elif hexid in _emergency_alerted:
        _emergency_alerted.discard(hexid)
```

## 4. Nytt /api/matrix-endepunkt (rundt linje 650-653)

**Finn:**
```python
        response["server_time"] = datetime.now(timezone.utc).isoformat()
        return jsonify(response)


@app.route("/api/range-log")
```

**Erstatt med:**
```python
        response["server_time"] = datetime.now(timezone.utc).isoformat()
        return jsonify(response)


@app.route("/api/matrix")
def api_matrix():
    with _lock:
        last_poll = _state["last_poll_success_epoch"]
        antenna_connected = last_poll is not None and (time.time() - last_poll) < ANTENNA_TIMEOUT_SECONDS
        return jsonify(matrix.build_matrix_response(_state, antenna_connected))


@app.route("/api/range-log")
```

## 5. requirements.txt

Legg til (hvis ikke allerede der):
```
werkzeug
```
(`requests` er allerede en avhengighet siden ADSBdb-oppslagene bruker den.)

## 6. Miljøvariabel som må settes

```
ADMIN_PASSWORD_HASH=<hash generert med werkzeug, se admin.py sin docstring>
```

Uten denne er `/admin` deaktivert (returnerer 503), resten av appen
fungerer som normalt.

## Viktig — hva som IKKE er gjort i denne runden

- **OpenSky som primærkilde** (bytte ut `poll_once()` sin `AIRCRAFT_JSON_URL`-henting
  med `opensky_client.py`) er bevisst utelatt her — det er en større endring
  av selve poll-logikken som fortjener egen testing, ikke noe å blande inn i
  samme patch som admin-panelet. `data_source`-valget i adminpanelet er
  forberedt (lagres i settings.json) men leses foreløpig ikke av `poll_once()`.
- Banner-feltet (`banner_text`/`banner_expires_at`) er med i `/api/matrix`,
  men selve ntfy-abonnementet (`ntfy_client.py`) er ikke testet mot en ekte
  ntfy-server fra min side — verifiser at SSE-strømmen faktisk kobler til
  din ntfy-instans (bytt `NTFY_BASE` i `ntfy_client.py` til din egen URL
  hvis du ikke bruker ntfy.sh direkte).
