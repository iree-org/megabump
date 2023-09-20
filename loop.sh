#!/bin/bash

set -euo pipefail
td="$(cd $(dirname $0) && pwd)"

while true; do
    echo "***********************************************************"
    echo " INTEGRATE ITERATION"
    echo "***********************************************************"

    ./auto_integrate.py status

    echo "***** PERFORMING BUILD AT CURRENT REVISION *****"
    ./build_and_validate.sh 2>&1 | tee $td/work/iree_build.log

    echo "***** ADVANCING *****"
    while true; do
        set +e
        ./auto_integrate.py next
        rc="$?"
        set -e
        if [ "$rc" == "99" ]; then
            echo "At ToT. Waiting..."
            sleep 300
        fi
        if [ "$rc" == "0" ]; then
            echo "Successful advance. Giving a beat..."
            sleep 10
            break
        fi
        echo "Could not advance."
        exit 1
    done
done

