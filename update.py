#!/usr/bin/env python3

import requests
import json
import dns.resolver
import random
import os
import sys
import ipaddress

dry_run = "--dry-run" in sys.argv or "-n" in sys.argv

whereami = os.path.dirname(os.path.realpath(__file__))
config_file = os.path.join(whereami, "config.json")
config = json.load(open(config_file, "r"))

entries = config["entries"]

baseurl = "https://dyn.dns.he.net/nic/update"

interface = str(config["interface"])

he_nameservers = ["ns1.he.net", "ns2.he.net", "ns3.he.net", "ns4.he.net", "ns5.he.net"]



def setupResolver():

	resolver = dns.resolver.Resolver()
	resolver.nameservers = ['8.8.8.8', '8.8.4.4']

	he_nameserver_ips = []

	#cheatsheet = ['216.218.130.2', '216.218.131.2', '216.218.132.2', '216.66.1.2', '216.66.80.18']
	#resolver.nameservers = cheatsheet
	#return resolver

	print("******* Setting up HE resolvers *******")

	for ns in he_nameservers:
		print("Looking up", ns,)
		answers = resolver.resolve(ns, "A")
		for data in answers:
			ns_ip = data.address
			print("got", ns_ip)
			he_nameserver_ips.append(ns_ip)

	random.shuffle(he_nameserver_ips)
	resolver.nameservers = he_nameserver_ips

	print("Using HE NS:", he_nameserver_ips)

	return resolver

def dnsLookup(name, resolver, rtype="A"):
	try:
		answers = resolver.resolve(name, rtype)
	except dns.resolver.NoNameservers:
		return None
	except dns.resolver.NoAnswer:
		return ""

	for data in answers:
           return data.address

def getInterfaceIP(interface):

	import socket
	import fcntl
	import struct

	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	return socket.inet_ntoa(fcntl.ioctl(
		s.fileno(),
		0x8915,  # SIOCGIFADDR
		struct.pack("256s", bytes(interface[:15], "utf-8"))
	)[20:24])

def getInterfaceIPv6(interface):
	# /proc/net/if_inet6 columns: addr(32 hex), ifindex, prefixlen, scope, flags, devname
	# Pick first global-scope (scope=="00"), non-deprecated, non-tentative address.
	try:
		with open("/proc/net/if_inet6") as f:
			for line in f:
				parts = line.split()
				if len(parts) < 6:
					continue
				addr_hex, _, _, scope, flags, dev = parts[:6]
				if dev != interface or scope != "00":
					continue
				if int(flags, 16) & 0x60:  # IFA_F_DEPRECATED | IFA_F_TENTATIVE
					continue
				return str(ipaddress.IPv6Address(int(addr_hex, 16)))
	except FileNotFoundError:
		return None
	return None

resolver = setupResolver()


myip = getInterfaceIP(interface)
myipv6 = getInterfaceIPv6(interface)

for entry in entries:
	hostname = entry["hostname"]

	print("*******", hostname, "*******")

	currentip = dnsLookup(hostname, resolver)

	print("Current:", currentip)
	print("My ip:", myip)

	if currentip is None:
		print("Lookup failed, skipping")
	elif currentip == myip:
		print("IP matches, skipping")
	else:
		print("New IP, updating")
		payload = {"hostname": hostname, "password": entry["password"], "myip": myip}
		if dry_run:
			print("[dry-run] would POST", baseurl, "with", {k: v for k, v in payload.items() if k != "password"})
		else:
			resp = requests.post(baseurl, data=payload)
			print(resp.status_code)

	if not entry.get("ipv6"):
		continue

	print("---", hostname, "(AAAA) ---")

	if myipv6 is None:
		print("No global IPv6 on interface, skipping AAAA")
		continue

	currentip6 = dnsLookup(hostname, resolver, "AAAA")

	print("Current:", currentip6)
	print("My ip:", myipv6)

	if currentip6 is None:
		print("AAAA lookup failed, skipping")
		continue

	if currentip6 == myipv6:
		print("IP matches, skipping")
		continue

	print("New IP, updating")
	payload = {"hostname": hostname, "password": entry["password"], "myip": myipv6}
	if dry_run:
		print("[dry-run] would POST", baseurl, "with", {k: v for k, v in payload.items() if k != "password"})
	else:
		resp = requests.post(baseurl, data=payload)
		print(resp.status_code)

