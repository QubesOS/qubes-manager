#!/usr/bin/sh
xl info|grep xen_version
uname -sr
echo "  "
echo "Installed Packages:  "
echo "  "
dnf list --installed |awk '$1~/qubes/ && $1!~/@qubes*/ { printf "%-50s\t%s \n",$1 ,$2}'




