#!/usr/bin/env python
# encoding: utf-8

import errno
import io
import socket
import time

import xmltok

from . import upnp
from . import sonos


DEFAULT_DISCOVER_TIMEOUT = 2


def _discover_ip(timeout=DEFAULT_DISCOVER_TIMEOUT):
    """Discover the IP of a single Sonos device on the network."""
    MCAST_GRP = '239.255.255.250'
    MCAST_PORT = 1900
    PLAYER_SEARCH = '\n'.join((
        'M-SEARCH * HTTP/1.1',
        'HOST: 239.255.255.250:1900',
        'MAN: "ssdp:discover"',
        'MX: 1',
        'ST: urn:schemas-upnp-org:device:ZonePlayer:1',
    )).encode('utf-8')

    # We have to set non-blocking mode and poll the socket, as MicroPython
    # doesn't give us anything better on the ESP8266
    # TODO: #7 - see if provisional select.poll() PR works well enough.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    # Send a few times, just in case UDP gives us trouble.
    for _ in range(3):
        sock.sendto(PLAYER_SEARCH, (MCAST_GRP, MCAST_PORT))

    start_time = time.time()
    end_time = start_time + timeout
    while True:
        if time.time() >= end_time:
            break
        try:
            data, (ip, port) = sock.recvfrom(1024)
        except OSError as e:
            # MicroPython returns ETIMEDOUT, but CPython 3.5 returns EAGAIN.
            if e.args[0] not in (errno.ETIMEDOUT, errno.EAGAIN):
                raise
        else:
            if b'Sonos' in data:
                return ip
            time.sleep(0.1)


def discover(timeout=DEFAULT_DISCOVER_TIMEOUT):
    """Discover Sonos devices on local network. Yields a Sonos instance for
    each coordinator on the network.

    Accepts optional `timeout` parameter, which gives total timeout in seconds.
    """
    ip = _discover_ip(timeout)
    assert ip is not None, 'Could not find Sonos device'

    topology = query_zone_group_topology(ip)
    for group in topology:
        coordinator_uuid = group['coordinator_uuid']
        players = {
            player_uuid: sonos.Sonos(player_uuid, player['ip'], player['name'])
            for player_uuid, player in group['players'].items()
        }
        coordinator = players[coordinator_uuid]
        for player_uuid, player in players.items():
            if player_uuid != coordinator_uuid:
                coordinator.add_player_to_group(player)
        yield coordinator


def _zone_group_topology_location_to_ip(location):
    """Takes a <ZoneGroupMember Location=> attribute and returns the IP of
    the player."""
    # Assume it is of the form http://ip:port/blah/, rather than supporting
    # any type of URL and needing `urllib.parse`. (It is available for MicroPython
    # but it requires a million dependencies).
    scheme_prefix = 'http://'
    assert location.startswith(scheme_prefix)
    location = location[len(scheme_prefix):]
    port_idx = location.find(':')
    return location[:port_idx]


def query_zone_group_topology(ip):
    """Queries the Zone Group Topology and returns a list of coordinators:

        > [
        >     # One per connected group of players.
        >     dict(coordinator_uuid, players=dict(
        >         # One per player in group, including coordinator. Keyed
        >         # on player UUID.
        >         player_uuid=dict(
                      dict(uuid, ip, player_name)
        >         )
        >     )
        > ]

    This is quite an expensive operation, so recommend this be done once and
    used to instantiate Sonos instances. This function is also very gnarly,
    as the lack of XML parser for MicroPython makes it difficult. (I really
    don't want to write an XML parser, as I'll do it wrong...)
    """
    base_url = sonos.BASE_URL_TEMPLATE % ip
    response = upnp.send_command(
        base_url + '/ZoneGroupTopology/Control',
        'ZoneGroupTopology', 1, 'GetZoneGroupState', []
    )

    # Yes. This is XML serialized as a string inside an XML UPnP response.
    xml_string = response['ZoneGroupState']
    tokens = xmltok.tokenize(io.StringIO(xml_string))

    # This is getting silly. It might be time to write a very light-weight
    # XML parser?
    coordinators = []
    token, value, *rest = next(tokens)
    while True:
        coordinator_uuid = None
        # Find <ZoneGroup>, or give up if we've seen the last one (or none!)
        try:
            while not (token == xmltok.START_TAG and value == ('', 'ZoneGroup')):
                token, value, *rest = next(tokens)
        except StopIteration:
            break
        # Find Coordinator= attribute.
        while not (token == xmltok.ATTR and value == ('', 'Coordinator')):
            token, value, *rest = next(tokens)
        coordinator_uuid, *_ = rest
        # Parse child-tags until we get </ZoneGroup>
        players = dict()
        while not (token == xmltok.END_TAG and value == ('', 'ZoneGroup')):
            token, value, *rest = next(tokens)
            # Find <ZoneGroupMember>
            if token == xmltok.START_TAG and value == ('', 'ZoneGroupMember'):
                # As this is a self-closing tag, xmltok never gives us an end
                # token. Once we have all the attributes we need, move onto
                # the next <ZoneGroupMember>.
                player_uuid = player_name = player_ip = None
                while not all((player_uuid, player_name, player_ip)):
                    token, value, *rest = next(tokens)
                    if token == xmltok.ATTR:
                        if value == ('', 'UUID'):
                            player_uuid, *_ = rest
                        elif value == ('', 'ZoneName'):
                            player_name, *_ = rest
                        elif value == ('', 'Location'):
                            location, *_ = rest
                            player_ip = _zone_group_topology_location_to_ip(location)
                players[player_uuid] = dict(
                    uuid=player_uuid,
                    name=player_name,
                    ip=player_ip
                )

        # We've finished parsing information about the <ZoneGroup>.
        coordinators.append(dict(
            coordinator_uuid=coordinator_uuid,
            players=players
        ))

    return coordinators
