#!/bin/sh

#args:
# 1) device path
# 2) mountpoint name

#check if path exists
if [ ! -e $1 ]; then
    exit 1; #no such path
fi

#check if luks-encrypted
if sudo cryptsetup isLuks $1 ; then
    # Is a luks device
    if ! kdialog --password "Please unlock the LUKS-encrypted $1 device:" | sudo pmount $1 $2 ; then
        exit 1;
    fi
else
    #not luks!
    if ! sudo pmount $1 $2 ; then
        exit 1;
    fi
fi

#all ok :)
exit 0;

