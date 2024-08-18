#!/usr/bin/env python3

import requests
import json
import dns.resolver
import random
import os

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
		answers = resolver.query(ns, "A")
		for data in answers:
			ns_ip = data.address
			print("got", ns_ip)
			he_nameserver_ips.append(ns_ip)

	random.shuffle(he_nameserver_ips)
	resolver.nameservers = he_nameserver_ips

	print("Using HE NS:", he_nameserver_ips)

	return resolver

def dnsLookup(name, resolver):
	try:
		answers = resolver.query(name, "A")
	except dns.resolver.NoNameservers:
		return None

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

resolver = setupResolver()


myip = getInterfaceIP(interface)

for entry in entries:
	hostname = entry["hostname"]

	print("*******", hostname, "*******")

	currentip = dnsLookup(hostname, resolver)

	print("Current:", currentip)
	print("My ip:", myip)

	if currentip is None:
		print("Lookup failed, skipping")
		continue

	if currentip == myip:
		print("IP matches, skipping")
		continue

	print("New IP, updating")

	entry["myip"] = myip

	resp = requests.post(baseurl, data=entry)

	print(resp.status_code)

