#!/bin/bash

set -e
td="$(cd $(dirname $0) && pwd)"

while true; do
    echo "***********************************************************"
    echo " INTEGRATE ITERATION"
    echo "***********************************************************"

    ./auto_integrate.py status

    echo "***** PERFORMING BUILD AT CURRENT REVISION *****"
    ./build_and_validate.sh

    echo "***** ADVANCING *****"
    ./auto_integrate.py next

    echo "Waiting..."
    sleep 10
done

