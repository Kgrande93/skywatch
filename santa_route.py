# Santa's Christmas route - one entry per country he visits.
#
# Each stop's arrival time is defined in THAT COUNTRY'S OWN LOCAL TIME AND
# TIMEZONE (not the server's TIMEZONE setting), since the whole point is
# that Santa arrives at the moment each country's own Christmas tradition
# calls for - evening of Dec 24 for most of Europe/Latin America, morning
# of Dec 25 for the Anglophone world, midnight for most of Latin America.
#
# Countries where a different figure delivers gifts on a different date
# entirely (Netherlands/Belgium: Sinterklaas Dec 5-6, Spain: Three Kings
# Jan 6, Russia/Serbia/Georgia/Armenia: New Year or Jan 7 Orthodox Christmas,
# Greece/Cyprus: Jan 1 St Basil, Ethiopia/Egypt: Jan 7) are deliberately
# NOT included here - Santa doesn't visit them on this route.
#
# This is a representative global route (~60 countries covering every
# researched region/tradition), not an exhaustive list of all ~195
# countries - add more entries in the same format if you want fuller
# coverage. Fields per stop:
#   country   - display name shown on screen
#   lat, lon  - representative coordinates (usually the capital)
#   timezone  - IANA timezone name for that country
#   day       - day in December (24 or 25) gifts are given
#   hour, minute - local time of the gift-giving moment in that timezone

STOPS = [
    # --- Pacific / first to celebrate ---
    {"country": "Kiribati", "lat": 1.33, "lon": 173.0, "timezone": "Pacific/Tarawa", "day": 24, "hour": 20, "minute": 0},
    {"country": "Samoa", "lat": -13.83, "lon": -171.76, "timezone": "Pacific/Apia", "day": 24, "hour": 20, "minute": 0},
    {"country": "Tonga", "lat": -21.14, "lon": -175.2, "timezone": "Pacific/Tongatapu", "day": 24, "hour": 20, "minute": 0},
    {"country": "New Zealand", "lat": -41.29, "lon": 174.78, "timezone": "Pacific/Auckland", "day": 25, "hour": 7, "minute": 0},
    {"country": "Fiji", "lat": -18.14, "lon": 178.44, "timezone": "Pacific/Fiji", "day": 25, "hour": 7, "minute": 0},

    # --- Australia / East Asia ---
    {"country": "Australia", "lat": -33.87, "lon": 151.21, "timezone": "Australia/Sydney", "day": 25, "hour": 7, "minute": 0},
    {"country": "Japan", "lat": 35.68, "lon": 139.69, "timezone": "Asia/Tokyo", "day": 24, "hour": 19, "minute": 0},
    {"country": "South Korea", "lat": 37.57, "lon": 126.98, "timezone": "Asia/Seoul", "day": 25, "hour": 8, "minute": 0},
    {"country": "Philippines", "lat": 14.6, "lon": 120.98, "timezone": "Asia/Manila", "day": 25, "hour": 0, "minute": 0},
    {"country": "China", "lat": 31.23, "lon": 121.47, "timezone": "Asia/Shanghai", "day": 24, "hour": 19, "minute": 0},
    {"country": "Singapore", "lat": 1.35, "lon": 103.82, "timezone": "Asia/Singapore", "day": 25, "hour": 7, "minute": 0},
    {"country": "Malaysia", "lat": 3.14, "lon": 101.69, "timezone": "Asia/Kuala_Lumpur", "day": 25, "hour": 7, "minute": 0},
    {"country": "Indonesia", "lat": -6.21, "lon": 106.85, "timezone": "Asia/Jakarta", "day": 25, "hour": 7, "minute": 0},
    {"country": "Thailand", "lat": 13.75, "lon": 100.5, "timezone": "Asia/Bangkok", "day": 25, "hour": 7, "minute": 0},
    {"country": "Vietnam", "lat": 21.03, "lon": 105.85, "timezone": "Asia/Ho_Chi_Minh", "day": 24, "hour": 19, "minute": 0},

    # --- South Asia ---
    {"country": "India", "lat": 28.61, "lon": 77.21, "timezone": "Asia/Kolkata", "day": 25, "hour": 7, "minute": 0},
    {"country": "Sri Lanka", "lat": 6.93, "lon": 79.85, "timezone": "Asia/Colombo", "day": 25, "hour": 7, "minute": 0},
    {"country": "Bangladesh", "lat": 23.81, "lon": 90.41, "timezone": "Asia/Dhaka", "day": 25, "hour": 7, "minute": 0},
    {"country": "Pakistan", "lat": 33.68, "lon": 73.05, "timezone": "Asia/Karachi", "day": 25, "hour": 7, "minute": 0},

    # --- Middle East ---
    {"country": "United Arab Emirates", "lat": 24.47, "lon": 54.37, "timezone": "Asia/Dubai", "day": 25, "hour": 7, "minute": 0},
    {"country": "Lebanon", "lat": 33.89, "lon": 35.5, "timezone": "Asia/Beirut", "day": 25, "hour": 7, "minute": 0},

    # --- Africa ---
    {"country": "Kenya", "lat": -1.29, "lon": 36.82, "timezone": "Africa/Nairobi", "day": 25, "hour": 7, "minute": 0},
    {"country": "Nigeria", "lat": 9.08, "lon": 7.4, "timezone": "Africa/Lagos", "day": 25, "hour": 7, "minute": 0},
    {"country": "Ghana", "lat": 5.6, "lon": -0.19, "timezone": "Africa/Accra", "day": 25, "hour": 7, "minute": 0},
    {"country": "Tanzania", "lat": -6.8, "lon": 39.28, "timezone": "Africa/Dar_es_Salaam", "day": 25, "hour": 7, "minute": 0},
    {"country": "South Africa", "lat": -25.75, "lon": 28.19, "timezone": "Africa/Johannesburg", "day": 25, "hour": 7, "minute": 0},

    # --- Nordics (evening Dec 24, well-documented times) ---
    {"country": "Finland", "lat": 60.17, "lon": 24.94, "timezone": "Europe/Helsinki", "day": 24, "hour": 18, "minute": 0},
    {"country": "Sweden", "lat": 59.33, "lon": 18.06, "timezone": "Europe/Stockholm", "day": 24, "hour": 16, "minute": 0},
    {"country": "Norway", "lat": 59.91, "lon": 10.75, "timezone": "Europe/Oslo", "day": 24, "hour": 17, "minute": 0},
    {"country": "Denmark", "lat": 55.68, "lon": 12.57, "timezone": "Europe/Copenhagen", "day": 24, "hour": 18, "minute": 0},
    {"country": "Iceland", "lat": 64.15, "lon": -21.94, "timezone": "Atlantic/Reykjavik", "day": 24, "hour": 18, "minute": 0},

    # --- Central Europe (evening Dec 24) ---
    {"country": "Germany", "lat": 52.52, "lon": 13.4, "timezone": "Europe/Berlin", "day": 24, "hour": 18, "minute": 0},
    {"country": "Austria", "lat": 48.21, "lon": 16.37, "timezone": "Europe/Vienna", "day": 24, "hour": 18, "minute": 0},
    {"country": "Switzerland", "lat": 46.95, "lon": 7.45, "timezone": "Europe/Zurich", "day": 24, "hour": 18, "minute": 0},
    {"country": "Poland", "lat": 52.23, "lon": 21.01, "timezone": "Europe/Warsaw", "day": 24, "hour": 17, "minute": 0},
    {"country": "Czech Republic", "lat": 50.08, "lon": 14.44, "timezone": "Europe/Prague", "day": 24, "hour": 17, "minute": 0},
    {"country": "Slovakia", "lat": 48.15, "lon": 17.11, "timezone": "Europe/Bratislava", "day": 24, "hour": 17, "minute": 0},
    {"country": "Hungary", "lat": 47.5, "lon": 19.05, "timezone": "Europe/Budapest", "day": 24, "hour": 18, "minute": 0},

    # --- Baltics ---
    {"country": "Estonia", "lat": 59.44, "lon": 24.75, "timezone": "Europe/Tallinn", "day": 24, "hour": 18, "minute": 0},
    {"country": "Latvia", "lat": 56.95, "lon": 24.11, "timezone": "Europe/Riga", "day": 24, "hour": 18, "minute": 0},
    {"country": "Lithuania", "lat": 54.69, "lon": 25.28, "timezone": "Europe/Vilnius", "day": 24, "hour": 18, "minute": 0},

    # --- Southern / Western Europe ---
    {"country": "Portugal", "lat": 38.72, "lon": -9.14, "timezone": "Europe/Lisbon", "day": 24, "hour": 22, "minute": 0},
    {"country": "Italy", "lat": 41.9, "lon": 12.5, "timezone": "Europe/Rome", "day": 24, "hour": 20, "minute": 0},
    {"country": "Croatia", "lat": 45.81, "lon": 15.98, "timezone": "Europe/Zagreb", "day": 24, "hour": 18, "minute": 0},
    {"country": "Slovenia", "lat": 46.05, "lon": 14.5, "timezone": "Europe/Ljubljana", "day": 24, "hour": 18, "minute": 0},
    {"country": "France", "lat": 48.85, "lon": 2.35, "timezone": "Europe/Paris", "day": 24, "hour": 22, "minute": 0},
    {"country": "Bulgaria", "lat": 42.7, "lon": 23.32, "timezone": "Europe/Sofia", "day": 24, "hour": 19, "minute": 0},
    {"country": "Romania", "lat": 44.43, "lon": 26.1, "timezone": "Europe/Bucharest", "day": 24, "hour": 19, "minute": 0},
    {"country": "Ukraine", "lat": 50.45, "lon": 30.52, "timezone": "Europe/Kyiv", "day": 25, "hour": 7, "minute": 0},

    # --- UK / Ireland (morning Dec 25) ---
    {"country": "United Kingdom", "lat": 51.51, "lon": -0.13, "timezone": "Europe/London", "day": 25, "hour": 7, "minute": 0},
    {"country": "Ireland", "lat": 53.35, "lon": -6.26, "timezone": "Europe/Dublin", "day": 25, "hour": 7, "minute": 0},

    # --- Latin America (midnight Dec 24->25) ---
    {"country": "Mexico", "lat": 19.43, "lon": -99.13, "timezone": "America/Mexico_City", "day": 25, "hour": 0, "minute": 0},
    {"country": "Guatemala", "lat": 14.63, "lon": -90.51, "timezone": "America/Guatemala", "day": 25, "hour": 0, "minute": 0},
    {"country": "Costa Rica", "lat": 9.93, "lon": -84.08, "timezone": "America/Costa_Rica", "day": 25, "hour": 0, "minute": 0},
    {"country": "Panama", "lat": 8.98, "lon": -79.52, "timezone": "America/Panama", "day": 25, "hour": 0, "minute": 0},
    {"country": "Colombia", "lat": 4.71, "lon": -74.07, "timezone": "America/Bogota", "day": 25, "hour": 0, "minute": 0},
    {"country": "Venezuela", "lat": 10.5, "lon": -66.92, "timezone": "America/Caracas", "day": 25, "hour": 0, "minute": 0},
    {"country": "Ecuador", "lat": -0.23, "lon": -78.52, "timezone": "America/Guayaquil", "day": 25, "hour": 0, "minute": 0},
    {"country": "Peru", "lat": -12.05, "lon": -77.04, "timezone": "America/Lima", "day": 25, "hour": 0, "minute": 0},
    {"country": "Bolivia", "lat": -16.5, "lon": -68.15, "timezone": "America/La_Paz", "day": 25, "hour": 0, "minute": 0},
    {"country": "Brazil", "lat": -23.55, "lon": -46.63, "timezone": "America/Sao_Paulo", "day": 25, "hour": 0, "minute": 0},
    {"country": "Chile", "lat": -33.45, "lon": -70.67, "timezone": "America/Santiago", "day": 25, "hour": 0, "minute": 0},
    {"country": "Argentina", "lat": -34.6, "lon": -58.38, "timezone": "America/Argentina/Buenos_Aires", "day": 25, "hour": 0, "minute": 0},
    {"country": "Uruguay", "lat": -34.9, "lon": -56.16, "timezone": "America/Montevideo", "day": 25, "hour": 0, "minute": 0},
    {"country": "Dominican Republic", "lat": 18.49, "lon": -69.93, "timezone": "America/Santo_Domingo", "day": 25, "hour": 0, "minute": 0},

    # --- North America (morning Dec 25) ---
    {"country": "United States", "lat": 38.9, "lon": -77.04, "timezone": "America/New_York", "day": 25, "hour": 7, "minute": 0},
    {"country": "Canada", "lat": 43.65, "lon": -79.38, "timezone": "America/Toronto", "day": 25, "hour": 7, "minute": 0},

    # --- Pacific tail end (last to celebrate) ---
    {"country": "United States (Alaska)", "lat": 61.22, "lon": -149.9, "timezone": "America/Anchorage", "day": 25, "hour": 7, "minute": 0},
    {"country": "United States (Hawaii)", "lat": 21.31, "lon": -157.86, "timezone": "Pacific/Honolulu", "day": 25, "hour": 7, "minute": 0},
]
