#!/usr/bin/env python3

"""
Script that opens the Hetzner Cloud Hosting firewall on game startup
"""

import os
import sys
from typing import Optional, List

import hcloud
from hcloud.actions.client import BoundAction
from hcloud.firewalls.domain import FirewallRule

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config

config.set_redis_clientname('Firewall-Hetzner-Control')
config.EXTERNAL_TIMER = True


HCLOUD_TOKEN = os.environ['HCLOUD_TOKEN']
HCLOUD_FIREWALL_NAME = 'Allow SSH/VPN Only'
SOURCE_IPS = ['0.0.0.0/0', '::/0']


def assert_actions(actions: List[BoundAction]):
	for action in actions:
		action.wait_until_finished(10)


def update_state(state: str):
	"""
	:param state: "on" or "team" or "off"
	:return:
	"""
	allow_ssh = state == 'on' or state == 'team'
	client = hcloud.Client(token=HCLOUD_TOKEN, poll_interval=2)
	firewall = client.firewalls.get_by_name(HCLOUD_FIREWALL_NAME)
	rule: FirewallRule
	ssh_rule: Optional[FirewallRule] = None
	for rule in firewall.rules:
		if rule.protocol == FirewallRule.PROTOCOL_TCP and rule.direction == FirewallRule.DIRECTION_IN and rule.port == '22' and rule.source_ips == SOURCE_IPS:
			ssh_rule = rule
	if allow_ssh == (ssh_rule is not None):
		print('[-]   No change necessary, SSH is ' + ('allowed' if ssh_rule is not None else 'blocked'))
	elif allow_ssh and ssh_rule is None:
		rules = firewall.rules + [FirewallRule(FirewallRule.DIRECTION_IN, FirewallRule.PROTOCOL_TCP, SOURCE_IPS, '22', description='Open SSH access')]
		assert_actions(firewall.set_rules(rules))
		print('[OK]  SSH has been allowed')
	elif not allow_ssh and ssh_rule is not None:
		rules = [rule for rule in firewall.rules if rule != ssh_rule]
		assert_actions(firewall.set_rules(rules))
		print('[OK]  SSH has been blocked')


def main():
	print('      Connecting...')
	redis = config.get_redis_connection()
	state_bytes = redis.get('network:state')
	state: str = state_bytes.decode() if state_bytes else None
	if state is None:
		redis.set('network:state', 'off')
		state = 'off'
	update_state(state)

	pubsub = redis.pubsub()
	pubsub.subscribe('network:state')
	for item in pubsub.listen():
		if item['type'] == 'message':
			print(f'[debug] message {repr(item["channel"])}, data {repr(item["data"])}')
			if item['channel'] == b'network:state':
				update_state(item['data'].decode())


if __name__ == '__main__':
	main()
