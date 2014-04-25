# Copyright 2013 Openstack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
import mock
from mock import patch
from tests import test_base
import webob.exc

from wafflehaus.nova.networking import detach_network_check


class FakeContext(object):
    project_id = '123456'


class MockedVIFInfo(dict):
    def __init__(self, vif_id, net_id):
        self['address'] = '196.168.1.1'
        self['id'] = vif_id
        self['network'] = {'id': net_id, 'label': 'nw_label'}

    def fixed_ips(self):
        return [{'address': '192.168.1.1'}]


class TestDetachNetworkCheck(test_base.TestBase):

    def create_patch(self, name, func=None):
        patcher = patch(name)
        thing = patcher.start()
        self.addCleanup(patcher.stop)
        return thing

    def setUp(self):
        self.app = mock.Mock()
        self.pkg = 'wafflehaus.nova.networking.detach_network_check'
        self.m_get_instance = self.create_patch(
            '%s.DetachNetworkCheck._get_instance' % self.pkg)
        self.m_get_instance.return_value = {'hahaha': 'derp'}

        self.m_get_context = self.create_patch(
            '%s.DetachNetworkCheck._get_context' % self.pkg)
        self.m_get_context.return_value = FakeContext()

        self.server_id = '12345678-1234-1234-1234-123456789012'

        self.vif_id = '12345678-1234-1234-1234-123456789012'
        self.bad_vif_id = '12345678-0000-1234-1234-123456789012'

        self.reqnet_id = '12345678-1234-1234-1234-123456789012'
        self.not_reqnet_id = '00000000-1234-1234-1234-123456789012'

        self.good_url = '123456/servers/%s/os-virtual-interfacesv2/%s' % (
            self.server_id, self.vif_id)
        self.bad_url = '123456/servers/%s/os-virtual-interfacesv2/%s' % (
            self.server_id, self.bad_vif_id)
        self.bad_url2 = '123456/servers/%s/os-some-other-extension/%s' % (
            self.server_id, self.bad_vif_id)
        self.not_uuid = '123456/servers/%s/os-virtual-interfacesv2/%s' % (
            self.server_id, 'derp')
        self.not_uuid2 = '123456/servers/%s/os-virtual-interfacesv2/%s' % (
            'derp', self.vif_id)

        self.empty_nw = []
        self.bad_vif_good_nw = [MockedVIFInfo(self.bad_vif_id, self.reqnet_id)]
        self.good_vif_bad_nw = [MockedVIFInfo(self.vif_id, self.not_reqnet_id)]
        self.good_nw = [MockedVIFInfo(self.vif_id, self.reqnet_id)]
        self.bad_nw = [MockedVIFInfo(self.bad_vif_id, self.not_reqnet_id)]
        self.multi_nw1 = [MockedVIFInfo(self.vif_id, self.reqnet_id),
                          MockedVIFInfo(self.bad_vif_id, self.not_reqnet_id)]
        self.multi_nw2 = [MockedVIFInfo(self.vif_id, self.not_reqnet_id),
                          MockedVIFInfo(self.bad_vif_id, self.not_reqnet_id)]
        self.conf = {'required_nets': self.reqnet_id}

    def test_create_filter(self):
        result = detach_network_check.filter_factory(self.conf)(self.app)
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.required_networks)
        self.assertTrue(self.reqnet_id in result.required_networks)

    def test_run_on_deletes(self):
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = self.empty_nw

        result = detach_network_check.filter_factory(self.conf)(self.app)
        result.__call__.request(self.good_url, method='POST')
        self.assertEqual(0, self.m_get_context.call_count)
        self.assertEqual(self.app, result.app)
        result.__call__.request(self.good_url, method='PUT')
        self.assertEqual(0, self.m_get_context.call_count)
        self.assertEqual(self.app, result.app)
        result.__call__.request(self.good_url, method='GET')
        self.assertEqual(0, self.m_get_context.call_count)
        self.assertEqual(self.app, result.app)
        result.__call__.request(self.good_url, method='DELETE')
        self.assertEqual(1, self.m_get_context.call_count)

    def test_filtering_requests(self):
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = self.empty_nw

        result = detach_network_check.filter_factory(self.conf)(self.app)
        result.__call__.request('/something', method='DELETE')
        self.assertEqual(1, self.m_get_context.call_count)
        self.assertEqual(0, self.m_get_instance.call_count)
        result.__call__.request(self.good_url, method='DELETE')
        self.assertEqual(2, self.m_get_context.call_count)
        self.assertEqual(1, self.m_get_instance.call_count)

    def test_empty_network_info(self):
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = self.empty_nw

        result = detach_network_check.filter_factory(self.conf)(self.app)
        resp = result.__call__.request(self.good_url, method='DELETE')
        self.assertEqual(self.app, resp)

    def test_nonempty_network_info(self):
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = self.good_nw

        result = detach_network_check.filter_factory(self.conf)(self.app)
        resp = result.__call__.request(self.good_url, method='DELETE')
        self.assertNotEqual(self.app, resp)
        self.assertTrue(isinstance(resp, webob.exc.HTTPForbidden))

    def test_not_matching_vif(self):
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = self.good_nw

        result = detach_network_check.filter_factory(self.conf)(self.app)
        resp = result.__call__.request(self.bad_url, method='DELETE')
        self.assertEqual(self.app, resp)

    def test_not_matching_vif2(self):
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = self.bad_vif_good_nw

        result = detach_network_check.filter_factory(self.conf)(self.app)
        resp = result.__call__.request(self.good_url, method='DELETE')
        self.assertEqual(self.app, resp)

    def test_not_matching_network(self):
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = self.good_vif_bad_nw

        result = detach_network_check.filter_factory(self.conf)(self.app)
        resp = result.__call__.request(self.good_url, method='DELETE')
        self.assertEqual(self.app, resp)

    def test_multi_vif_matching_network(self):
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = self.multi_nw1

        result = detach_network_check.filter_factory(self.conf)(self.app)
        resp = result.__call__.request(self.good_url, method='DELETE')
        self.assertNotEqual(self.app, resp)
        self.assertTrue(isinstance(resp, webob.exc.HTTPForbidden))

    def test_multi_vif_no_match(self):
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = self.multi_nw2

        result = detach_network_check.filter_factory(self.conf)(self.app)
        resp = result.__call__.request(self.good_url, method='DELETE')
        self.assertEqual(self.app, resp)

    def test_vif_not_uuid(self):
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = self.multi_nw2

        result = detach_network_check.filter_factory(self.conf)(self.app)
        resp = result.__call__.request(self.not_uuid, method='DELETE')
        self.assertEqual(1, self.m_get_context.call_count)
        self.assertEqual(0, self.m_get_instance.call_count)
        self.assertEqual(self.app, resp)

    def test_server_not_uuid(self):
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = self.multi_nw2

        result = detach_network_check.filter_factory(self.conf)(self.app)
        resp = result.__call__.request(self.not_uuid2, method='DELETE')
        self.assertEqual(1, self.m_get_context.call_count)
        self.assertEqual(0, self.m_get_instance.call_count)
        self.assertEqual(self.app, resp)

    def test_incorrect_url(self):
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = self.multi_nw2

        result = detach_network_check.filter_factory(self.conf)(self.app)
        resp = result.__call__.request(self.bad_url2, method='DELETE')
        self.assertEqual(1, self.m_get_context.call_count)
        self.assertEqual(0, self.m_get_instance.call_count)
        self.assertEqual(self.app, resp)

    def test_no_context_found(self):
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = self.multi_nw2
        self.m_get_context.return_value = None

        result = detach_network_check.filter_factory(self.conf)(self.app)
        resp = result.__call__.request(self.good_url, method='DELETE')
        self.assertEqual(1, self.m_get_context.call_count)
        self.assertEqual(0, self.m_get_instance.call_count)
        self.assertEqual(self.app, resp)
