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

# Optional healthchecks.io URL: pinged after each run (URL on success, URL/fail on failure),
# with the run's output as the body.
ping_url = config.get("healthcheck_ping_url") or None

he_nameservers = ["ns1.he.net", "ns2.he.net", "ns3.he.net", "ns4.he.net", "ns5.he.net"]

output = []   # everything logged this run, sent along with the ping
failed = False


def log(*args):
	line = " ".join(str(a) for a in args)
	output.append(line)
	print(line, flush=True)


def fail(*args):
	global failed
	failed = True
	log("FAILED:", *args)


def ping(ok):
	url = ping_url if ok else ping_url.rstrip("/") + "/fail"
	try:
		requests.post(url, data="\n".join(output)[-10000:].encode(), timeout=10)
	except requests.RequestException as e:
		print("Healthcheck ping failed:", e, flush=True)


def setupResolver():

	resolver = dns.resolver.Resolver()
	resolver.nameservers = ['8.8.8.8', '8.8.4.4']

	he_nameserver_ips = []

	#cheatsheet = ['216.218.130.2', '216.218.131.2', '216.218.132.2', '216.66.1.2', '216.66.80.18']
	#resolver.nameservers = cheatsheet
	#return resolver

	log("******* Setting up HE resolvers *******")

	for ns in he_nameservers:
		log("Looking up", ns)
		answers = resolver.resolve(ns, "A")
		for data in answers:
			ns_ip = data.address
			log("got", ns_ip)
			he_nameserver_ips.append(ns_ip)

	random.shuffle(he_nameserver_ips)
	resolver.nameservers = he_nameserver_ips

	log("Using HE NS:", he_nameserver_ips)

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

def update(hostname, password, ip):
	"""Ask HE to set hostname to ip. HE answers HTTP 200 with "good <ip>" or "nochg <ip>" on
	success, but also with errors like "badauth", "nohost" or "abuse"."""
	payload = {"hostname": hostname, "password": password, "myip": ip}
	if dry_run:
		log("[dry-run] would POST", baseurl, "with", {k: v for k, v in payload.items() if k != "password"})
		return
	try:
		resp = requests.post(baseurl, data=payload, timeout=30)
	except requests.RequestException as e:
		fail(hostname, "update request failed:", e)
		return
	answer = resp.text.strip()
	log(resp.status_code, answer)
	if resp.status_code != 200 or not answer.startswith(("good", "nochg")):
		fail(hostname, "HE answered:", resp.status_code, answer)

def run():
	resolver = setupResolver()

	try:
		myip = getInterfaceIP(interface)
	except OSError as e:
		myip = None
		fail("no IPv4 address on", interface, "-", e)
	myipv6 = getInterfaceIPv6(interface)

	for entry in entries:
		hostname = entry["hostname"]

		log("*******", hostname, "*******")

		if myip is not None:
			currentip = dnsLookup(hostname, resolver)

			log("Current:", currentip)
			log("My ip:", myip)

			if currentip is None:
				fail(hostname, "A lookup failed, skipping")
			elif currentip == myip:
				log("IP matches, skipping")
			else:
				log("New IP, updating")
				update(hostname, entry["password"], myip)

		if not entry.get("ipv6"):
			continue

		log("---", hostname, "(AAAA) ---")

		if myipv6 is None:
			fail(hostname, "no global IPv6 on interface, skipping AAAA")
			continue

		currentip6 = dnsLookup(hostname, resolver, "AAAA")

		log("Current:", currentip6)
		log("My ip:", myipv6)

		if currentip6 is None:
			fail(hostname, "AAAA lookup failed, skipping")
			continue

		if currentip6 == myipv6:
			log("IP matches, skipping")
			continue

		log("New IP, updating")
		update(hostname, entry["password"], myipv6)


try:
	run()
except Exception as e:
	fail("error:", repr(e))

if ping_url and not dry_run:
	ping(not failed)

sys.exit(1 if failed else 0)
