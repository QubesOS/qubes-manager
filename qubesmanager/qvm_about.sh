#!/usr/bin/sh

# SPDX-FileCopyrightText: 2015 Michael Carbone, <michael@qubes-os.org> et al.
#
# SPDX-License-Identifier: GPL-2.0-only

xl info|grep xen_version
uname -sr
echo "  "
echo "Installed Packages:  "
echo "  "
dnf list installed |awk '$1~/qubes/ && $1!~/@qubes*/ { printf "%-50s\t%s \n",$1 ,$2}'




