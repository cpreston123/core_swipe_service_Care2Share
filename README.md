# core_swipe_service_Care2Share

## Overview
Core swipe service for Care2Share Application (composite service).
Running on Port 8000.

### Running and Testing on VM
```
source venv/bin/activate
python3 main.py
^Z
bg %1
curl localhost:8000
fg %1
^C
```
On browser, access http://localhost:8000/


### Set up + Running Application Locally
```
sudo apt update

sudo apt install python3 python3-pip -y

git clone https://github.com/cpreston123/core_swipe_service_Care2Share.git

sudo apt install python3.12-venv

sudo python3 -m venv ./venv

source venv/bin/activate

pip install requirements.txt

python main.py

```
See above "Running and Testing on VM" to test application






