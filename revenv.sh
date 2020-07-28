#! /bin/bash

deactivate
rm -rf venv
python3 -mvenv venv
pip install --upgrade pip
pip install wheel
pip install -r requirements.txt
pip freeze -r requirements.txt > requirements-frozen.txt
