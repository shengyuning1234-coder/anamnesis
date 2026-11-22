#!/bin/bash
set -euo pipefail
/opt/anamnesis-venv/bin/python /opt/anamnesis/deploy/inject_theme.py
exec /opt/anamnesis-venv/bin/supervisord -n -c /opt/anamnesis/deploy/supervisord.conf
