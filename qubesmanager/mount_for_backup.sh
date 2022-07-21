#!/bin/sh

# SPDX-FileCopyrightText: 2015 Michael Carbone, <michael@qubes-os.org> et al.
#
# SPDX-License-Identifier: GPL-2.0-only


#args:
# 1) device path
# 2) mountpoint name

#check if path exists
if [ ! -e $1 ]; then
    exit 1; #no such path
fi

if type kdialog &> /dev/null; then
    PROMPT="kdialog --title Qubes --password"
else
    PROMPT="zenity --entry --title Qubes --hide-text --text"
fi


#check if luks-encrypted
if sudo cryptsetup isLuks $1 ; then
    # Is a luks device
    if ! $PROMPT "Please unlock the LUKS-encrypted $1 device:" | sudo pmount $1 $2 ; then
        exit 1
    fi
else
    #not luks!
    if ! sudo pmount $1 $2 ; then
        exit 1
    fi
fi

#all ok :)
exit 0

