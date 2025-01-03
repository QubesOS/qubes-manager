#!/bin/bash

python3 -m coverage run --omit="test-packages/*,qubesmanager/tests/*,*/core-admin-client/*" -m pytest -vv qubesmanager/tests
