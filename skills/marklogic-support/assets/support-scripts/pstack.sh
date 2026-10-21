#!/bin/bash

# root check
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root" 1>&2
   exit 1
fi

# default argument check
if [[ -z $1 ]]; then
        echo Usage: ./pstack.sh \[running time in seconds\]
        echo e.g. ./pstack.sh 60 \(runs the application for 1 minute before closing\)
        exit 1
fi

# global vars
TSTAMP=`date +"%H%M%S-%m-%d-%Y"`
INTERVAL=3 TIME=$1

# main
echo Support script started at: $TSTAMP - running for $TIME seconds with a sample every $INTERVAL seconds
mkdir /tmp/$TSTAMP

while [ $TIME -gt 0 ]; do
    date >> /tmp/$TSTAMP/pstack.log
    /etc/MarkLogic/proc-util.sh pstack >> /tmp/$TSTAMP/pstack.log
# For MarkLogic versions earlier than 11.3.1, or for any 11.3.x builds not based on RHEL9,
# the service command may also be used for this. In such cases, adjust the above command as follows:
# service MarkLogic pstack >> /tmp/$TSTAMP/pstack.log
    sleep $INTERVAL
    echo -e ". \c"
    let TIME-=$(($INTERVAL))
done
echo completed

# create zip
zip -9 -r /tmp/$TSTAMP.zip /tmp/$TSTAMP
echo /tmp/$TSTAMP.zip created
