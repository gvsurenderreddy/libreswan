/testing/guestbin/swan-prep
ipsec start
/testing/pluto/bin/wait-until-pluto-started
ipsec auto --add westnet-eastnet-ikev2-fallback
ipsec auto --status | grep westnet-eastnet-ikev2-fallback
echo "initdone"
