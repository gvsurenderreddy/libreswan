/testing/guestbin/swan-prep
fipscheck
ipsec start
/testing/pluto/bin/wait-until-pluto-started
ipsec auto --add westnet-eastnet
echo "initdone"
