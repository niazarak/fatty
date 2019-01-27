#!/usr/bin/env bash

coverage3 erase
find . -iname 'test_*.py' -type f -exec coverage3 run --omit */site-packages/* -a {}  \;
coverage3 report -m 