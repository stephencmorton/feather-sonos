#!/usr/bin/env python
# encoding: utf-8

import io
import unittest

import urequests

import sonos


class SonosSpeakerTests(unittest.TestCase):

    soap_response_template = (
        '<?xml version="1.0"?>'
        '<s:Envelope '
            'xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            '<s:Body>'
                '<u:{action}Response xmlns:u="urn:schemas-upnp-org:service:serviceType:v">'
                    '{args_xml}'
                '</u:{action}Response>'
            '</s:Body>'
        '</s:Envelope>'
    )
    argument_temlate = '<{name}>{value}</{name}>'

    def test_parse_upnp_response_no_arguments(self):
        """Passing a SOAP response with no arguments should give []"""
        soap_xml = self.soap_response_template.format(
            action='Pause', args_xml=''
        )
        resp = urequests.Response(io.StringIO(soap_xml))
        arguments = sonos.parse_upnp_response('Pause', resp)
        self.assertEqual(arguments, [])

    def test_parse_upnp_response_with_arguments(self):
        """Passing a SOAP response with some valid arguments should return them"""
        args = [
            dict(name='arg1', value='value1'),
            dict(name='arg2', value='value2'),
        ]
        args_xml = ''.join(
            self.argument_temlate.format(**arg)
            for arg in args
        )
        soap_xml = self.soap_response_template.format(
            action='Pause', args_xml=args_xml
        )
        resp = urequests.Response(io.StringIO(soap_xml))
        arguments = sonos.parse_upnp_response('Pause', resp)
        self.assertEqual(arguments, [
            (arg['name'], arg['value'])
            for arg in args
        ])

    def test_parse_upnp_response_with_invalid_xml(self):
        """Passing some invalid badly formed XML should cause it to give up"""
        with self.assertRaises(Exception):
            resp = urequests.Response(io.StringIO('<a>'))
            sonos.parse_upnp_response('Pause', resp)


if __name__ == '__main__':
    unittest.main()
