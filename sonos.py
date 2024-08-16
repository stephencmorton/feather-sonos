#!/usr/bin/env python
# encoding: utf-8

# import errno
import io
# import socket
# import time

import xmltok

import upnp
import discovery


BASE_URL_TEMPLATE = 'http://%s:1400'


class TrackInfo:
    """Information about the currently playing track."""

    def __init__(self, metadata, total_time, current_time):
        self.total_time = total_time
        self.current_time = current_time
        self._parse_metadata(metadata)

    def _parse_metadata(self, metadata):
        """Parse the relevant metadata out of a <DIDL-Lite> document."""
        tags_of_interest = {
            ('dc', 'creator'): 'artist',
            ('upnp', 'album'): 'album',
            ('dc', 'title'): 'title',
        }
        tokens = xmltok.tokenize(io.StringIO(metadata))
        token, value, *_ = next(tokens)
        while True:
            if token == xmltok.START_TAG:
                attrib = tags_of_interest.get(value)
                if attrib is not None:
                    # Assume the next token is the TEXT token. None of the tags
                    # we're interested in have any attributes, so this is probably true.
                    token, value, *_ = next(tokens)
                    assert token == xmltok.TEXT
                    setattr(self, attrib, value)
            try:
                token, value, *_ = next(tokens)
            except StopIteration:
                break

    def __repr__(self):
        return '<TrackInfo artist=\'%s\' album=\'%s\' title=\'%s\' position=%s/%s>' % (
            getattr(self, 'artist', 'unknown'),
            getattr(self, 'album','unknown'),
            self.title, self.current_time, self.total_time
        )


class Sonos:
    """Represents a Sonos device (usually a speaker).

    Usually you'd access the Sonos instance for the controller of a group. The
    other devices in the group are stored on `Sonos.other_players`.

    This class isn't really meant to manage group membership (as `soco.SoCo`
    instances do), and so it assumes group membership doesn't change after it's
    created.
    """

    def __init__(self, uuid, ip, name):
        self.uuid = uuid
        self.ip = ip
        self.name = name
        self.other_players = []
        self._base_url = BASE_URL_TEMPLATE % self.ip

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        # We really only need to check the UUIDs match, but we'll test all
        # of our important fields match, so that we can use this for asserts
        # in the tests.
        return (
            self.uuid == other.uuid and
            self.ip == other.ip and
            self.name == other.name
        )

    def __repr__(self):
        return '<Sonos uuid=%s, ip=%s, name=%s, other_players=%r>' % (
            self.uuid, self.ip, self.name, self.other_players
        )

    def add_player_to_group(self, player):
        self.other_players.append(player)

    def _issue_sonos_command(self, command, args=None, service='AVTransport'):
        if args is None:
            args = [('InstanceID', 0), ('Speed', 1)]
        # Play/Pause/Next are all very similar.
        return upnp.send_command(
            self._base_url + f'/MediaRenderer/{service}/Control',
            service, 1, command, args
        )

    def play(self):
        self._issue_sonos_command('Play')

    def pause(self):
        self._issue_sonos_command('Pause')

    def next(self):
        self._issue_sonos_command('Next')

    def vol_up(self, increment=5):
        'Increase the volume. Return new volume. 0-100'
        response = self._issue_sonos_command('SetRelativeVolume',
            args=[('Channel', 'Master'), ('InstanceID', 0), ('Adjustment', int(increment))],
            service='RenderingControl')
        return int(response['NewVolume'])

    def vol_down(self, increment=5):
        'Decrease the volume. Return new volume. 0-100'
        return self.vol_up(-increment)

    def get_current_track_info(self):
        response = self._issue_sonos_command('GetPositionInfo', [
            ('InstanceID', 0),
            ('Channel', 'Master')
        ])
        if 'TrackMetaData' not in response:
            # Nothing playing.
            return None

        return TrackInfo(
            response['TrackMetaData'], # DIDL-Lite XML
            response['TrackDuration'], # Total length
            response['RelTime'] # Current position
        )


if __name__ == '__main__':
    all_sonos = list(discovery.discover())
    for s in all_sonos:
        print(s)
    for s in all_sonos:
        print(f"{s.name:15s} : {s.get_current_track_info()}")
