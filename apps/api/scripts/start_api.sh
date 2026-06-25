#!/bin/sh
set -eu

/opt/venvs/api/bin/python -m app.db.startup
