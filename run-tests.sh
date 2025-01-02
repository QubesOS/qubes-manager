#!/bin/bash

python3 -m coverage run --omit="test-packages/*,qubesmanager/tests/*" -m pytest -vv qubesmanager/tests
