#!/bin/bash
# Run photon geocoder v3 - bypass proxy for direct Photon API access
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
export NO_PROXY='*'
cd /home/yy/qgis-data
exec python3 scripts/photon_geocode_v3.py --start 0 --chunk 3000
