#! /bin/bash

deactivate
rm -rf venv
python3 -mvenv venv
source venv/bin/activate
pip install --upgrade pip
pip install wheel
pip install -r requirements.txt
pip freeze -r requirements.txt > requirements-frozen.txt
