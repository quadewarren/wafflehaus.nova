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
import webob.exc

from wafflehaus.nova.networking import network_count_check
from wafflehaus import tests


class MockedVIFInfo(dict):
    def __init__(self, vif_id, net_id):
        self['address'] = '196.168.1.1'
        self['id'] = vif_id
        self['network'] = {'id': net_id, 'label': 'nw_label'}

    def fixed_ips(self):
        return [{'address': '192.168.1.1'}]


class FakeContext(object):

    def __init__(self, project=123456):
        self.project_id = project


class TestNetworkCountCheck(tests.TestCase):

    def setUp(self):
        self.app = mock.Mock()
        self.conf = {'enabled': 'true'}
        self.tenant_id = '123456'
        self.context = FakeContext(self.tenant_id)
        self.vifuuid = '12341234-1234-1234-1234-123412341234'
        self.adduuid = '99999999-9999-9999-9999-999999999999'
        self.pubuuid = '00000000-0000-0000-0000-000000000000'
        self.srvuuid = '11111111-1111-1111-1111-111111111111'

        core_path = 'wafflehaus.nova.networking'
        nova_path = 'wafflehaus.nova.nova_base.WafflehausNova'
        attach_path = 'network_count_check.AttachNetworkCountCheck'
        boot_path = 'network_count_check.BootNetworkCountCheck'
        self.attach_path = '%s.%s.check_networks' % (
            core_path, attach_path)
        self.boot_path = '%s.%s.check_networks' % (
            core_path, boot_path)
        self.get_instance_path = '%s._get_instance' % nova_path
        self.ctx_path = '%s._get_context' % nova_path

        self.boot_body1 = '{}'

    def test_initial_instance(self):
        result = network_count_check.filter_factory(self.conf)(self.app)
        self.assertIsNotNone(result)

    def test_return_app_on_missing_context(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = None

        result = network_count_check.filter_factory(self.conf)(self.app)
        result.__call__.request('/something', method='POST')
        self.assertEqual(1, m_ctx.call_count)
        self.assertEqual(self.app, result.app)

    def test_run_on_post(self):
        m_ctx = self.create_patch(self.ctx_path)

        result = network_count_check.filter_factory(self.conf)(self.app)
        result.__call__.request('/something', method='GET')
        self.assertEqual(0, m_ctx.call_count)
        self.assertEqual(self.app, result.app)
        result.__call__.request('/something', method='PUT')
        self.assertEqual(0, m_ctx.call_count)
        self.assertEqual(self.app, result.app)
        result.__call__.request('/something', method='DELETE')
        self.assertEqual(0, m_ctx.call_count)
        self.assertEqual(self.app, result.app)
        result.__call__.request('/something', method='POST')
        self.assertEqual(1, m_ctx.call_count)
        self.assertEqual(self.app, result.app)

    def test_pathing_properly(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        m_attach = self.create_patch(self.attach_path)
        m_boot = self.create_patch(self.boot_path)

        result = network_count_check.filter_factory(self.conf)(self.app)
        self.assertEqual(0, m_attach.call_count)
        self.assertEqual(0, m_boot.call_count)

        result.__call__.request('/%s/derp' % self.tenant_id, method='POST',
                                body=self.boot_body1)
        result.__call__.request('/%s/servers' % '909090', method='POST',
                                body=self.boot_body1)
        result.__call__.request('/%s/servers' % self.tenant_id, method='GET',
                                body=self.boot_body1)
        result.__call__.request('/%s/servers' % self.tenant_id, method='PUT',
                                body=self.boot_body1)
        result.__call__.request('/%s/servers' % self.tenant_id,
                                method='DELETE', body=self.boot_body1)
        goodurl = '/%s/servers/%s/os-virtual-interfacesv2'
        badurl = '/%s/servers/%s/os-virtual-interfaces'
        result.__call__.request(goodurl % ('909090', self.vifuuid),
                                method='POST', body=self.boot_body1)
        result.__call__.request(goodurl % (self.tenant_id, '1234'),
                                method='POST', body=self.boot_body1)
        result.__call__.request(badurl % (self.tenant_id, '1234'),
                                method='POST', body=self.boot_body1)
        self.assertEqual(0, m_attach.call_count)
        self.assertEqual(0, m_boot.call_count)

        result.__call__.request('/%s/servers' % self.tenant_id, method='POST',
                                body=self.boot_body1)
        self.assertEqual(0, m_attach.call_count)
        self.assertEqual(1, m_boot.call_count)

        result.__call__.request(goodurl % (self.tenant_id, self.vifuuid),
                                method='POST', body=self.boot_body1)
        self.assertEqual(1, m_attach.call_count)
        self.assertEqual(1, m_boot.call_count)

    def test_attach_checking_default_one_isolated_allowed(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        m_instance = self.create_patch(self.get_instance_path)
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = [MockedVIFInfo(self.vifuuid, self.pubuuid)]

        result = network_count_check.filter_factory(self.conf)(self.app)
        self.assertEqual(1, result.check_config.networks_max)

        body = '{"virtual_interface": {"network_id": "%s"}}'

        goodurl = '/%s/servers/%s/os-virtual-interfacesv2'
        vif = self.vifuuid
        resp = result.__call__.request(goodurl % (self.tenant_id, vif),
                                       method='POST', body=body % self.adduuid)
        self.assertEqual(1, m_instance.call_count)
        self.assertEqual(1, m_get_nwinfo.call_count)
        self.assertTrue(isinstance(resp, webob.exc.HTTPForbidden))
        self.assertTrue('be attached' in str(resp))

    def test_attach_checking_configured_two_allowed(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        m_instance = self.create_patch(self.get_instance_path)
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        vif_id = '12345678-1234-1234-1234-123456789012'
        net_id = '12345678-1234-1234-1234-123456789012'
        m_get_nwinfo.return_value = [MockedVIFInfo(vif_id, net_id)]

        conf = {'networks_max': '2', 'enabled': 'true'}
        result = network_count_check.filter_factory(conf)(self.app)
        self.assertEqual(2, result.check_config.networks_max)

        body = '{"virtual_interface": {"network_id": "%s"}}'

        goodurl = '/%s/servers/%s/os-virtual-interfacesv2'
        vif = self.vifuuid
        resp = result.__call__.request(goodurl % (self.tenant_id, vif),
                                       method='POST', body=body % self.adduuid)
        self.assertEqual(1, m_instance.call_count)
        self.assertEqual(1, m_get_nwinfo.call_count)
        self.assertEqual(self.app, resp)

    def test_attach_checking_configured_two_allowed_adding_third(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        m_instance = self.create_patch(self.get_instance_path)
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        vif_id1 = '12345678-1234-1234-1234-123456789012'
        vif_id2 = '12345678-0000-1234-1234-123456789012'
        net_id1 = '12345678-1234-0000-1234-123456789012'
        net_id2 = '12345678-1234-1234-0000-123456789012'
        m_get_nwinfo.return_value = [MockedVIFInfo(vif_id1, net_id1),
                                     MockedVIFInfo(vif_id2, net_id2)]
        conf = {'networks_max': '2', 'enabled': 'true'}
        result = network_count_check.filter_factory(conf)(self.app)
        self.assertEqual(2, result.check_config.networks_max)

        body = '{"virtual_interface": {"network_id": "%s"}}'

        goodurl = '/%s/servers/%s/os-virtual-interfacesv2'
        vif = self.vifuuid
        resp = result.__call__.request(goodurl % (self.tenant_id, vif),
                                       method='POST', body=body % self.adduuid)
        self.assertEqual(1, m_instance.call_count)
        self.assertEqual(1, m_get_nwinfo.call_count)
        self.assertTrue(isinstance(resp, webob.exc.HTTPForbidden))
        self.assertTrue('be attached' in str(resp))

    def test_attach_checking_configured_one_with_optional_nets(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        m_instance = self.create_patch(self.get_instance_path)
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = [MockedVIFInfo(self.vifuuid, self.pubuuid)]
        conf = {'optional_nets': self.pubuuid,
                'networks_max': '1', 'enabled': 'true'}
        result = network_count_check.filter_factory(conf)(self.app)
        self.assertEqual(1, result.check_config.networks_max)
        self.assertEqual(1, len(result.check_config.optional_networks))
        self.assertEqual(False, result.check_config.count_optional_nets)

        body = '{"virtual_interface": {"network_id": "%s"}}'

        goodurl = '/%s/servers/%s/os-virtual-interfacesv2'
        vif = self.vifuuid
        resp = result.__call__.request(goodurl % (self.tenant_id, vif),
                                       method='POST', body=body % self.adduuid)
        self.assertEqual(1, m_instance.call_count)
        self.assertEqual(1, m_get_nwinfo.call_count)
        self.assertEqual(self.app, resp)

    def test_attach_checking_configured_one_with_banned_nets(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        m_instance = self.create_patch(self.get_instance_path)
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = [MockedVIFInfo(self.vifuuid, self.srvuuid)]
        conf = {'banned_nets': self.pubuuid,
                'networks_max': '2', 'enabled': 'true'}
        result = network_count_check.filter_factory(conf)(self.app)
        self.assertEqual(2, result.check_config.networks_max)
        self.assertEqual(1, len(result.check_config.banned_networks))

        body = '{"virtual_interface": {"network_id": "%s"}}'

        goodurl = '/%s/servers/%s/os-virtual-interfacesv2'
        vif = self.vifuuid
        resp = result.__call__.request(goodurl % (self.tenant_id, vif),
                                       method='POST', body=body % self.pubuuid)
        self.assertEqual(1, m_instance.call_count)
        self.assertEqual(1, m_get_nwinfo.call_count)
        self.assertTrue(isinstance(resp, webob.exc.HTTPForbidden))
        self.assertTrue('not allowed' in str(resp))

    def test_attach_with_malformed_body_returns_app(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        m_instance = self.create_patch(self.get_instance_path)
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = [MockedVIFInfo(self.vifuuid, self.srvuuid)]
        conf = {'banned_nets': self.pubuuid,
                'networks_max': '2', 'enabled': 'true'}
        result = network_count_check.filter_factory(conf)(self.app)
        self.assertEqual(2, result.check_config.networks_max)
        self.assertEqual(1, len(result.check_config.banned_networks))

        body = '{"virtual_interface": {"network": "%s"}}'

        goodurl = '/%s/servers/%s/os-virtual-interfacesv2'
        vif = self.vifuuid
        resp = result.__call__.request(goodurl % (self.tenant_id, vif),
                                       method='POST', body=body % self.pubuuid)
        self.assertEqual(0, m_instance.call_count)
        self.assertEqual(0, m_get_nwinfo.call_count)
        self.assertEqual(self.app, resp)

    def test_attach_checking_default_one_isolated_allowed_from_none(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        m_instance = self.create_patch(self.get_instance_path)
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = []

        result = network_count_check.filter_factory(self.conf)(self.app)
        self.assertEqual(1, result.check_config.networks_max)

        body = '{"virtual_interface": {"network_id": "%s"}}'

        goodurl = '/%s/servers/%s/os-virtual-interfacesv2'
        vif = self.vifuuid
        resp = result.__call__.request(goodurl % (self.tenant_id, vif),
                                       method='POST', body=body % self.adduuid)
        self.assertEqual(1, m_instance.call_count)
        self.assertEqual(1, m_get_nwinfo.call_count)
        self.assertEqual(self.app, resp)

    def test_attach_no_body_returns_app(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        m_get_nwinfo = self.create_patch(
            'nova.compute.utils.get_nw_info_for_instance')
        m_get_nwinfo.return_value = []

        result = network_count_check.filter_factory(self.conf)(self.app)

        body = ''

        goodurl = '/%s/servers/%s/os-virtual-interfacesv2'
        vif = self.vifuuid
        resp = result.__call__.request(goodurl % (self.tenant_id, vif),
                                       method='POST', body=body)
        self.assertEqual(self.app, resp)

    def test_boot_at_least_one_network(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        conf = {'networks_min': '1', 'enabled': 'true'}

        result = network_count_check.filter_factory(conf)(self.app)
        self.assertEqual(1, result.check_config.networks_min)

        body = '{"server": {"networks":[]}}'

        goodurl = '/%s/servers'
        resp = result.__call__.request(goodurl % self.tenant_id, method='POST',
                                       body=body)
        self.assertTrue(isinstance(resp, webob.exc.HTTPForbidden))
        self.assertTrue('be attached' in str(resp))

    def test_boot_suports_no_network_in_body_with_requires(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        conf = {'networks_min': '0', 'networks_max': '2',
                'required_nets': self.pubuuid, 'enabled': 'true'}

        result = network_count_check.filter_factory(conf)(self.app)
        self.assertEqual(0, result.check_config.networks_min)

        body = '{"server": {}}'

        goodurl = '/%s/servers'
        resp = result.__call__.request(goodurl % self.tenant_id, method='POST',
                                       body=body)
        self.assertEqual(self.app, resp)

    def test_boot_suports_no_networks(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        conf = {'networks_min': '0', 'enabled': 'true'}

        result = network_count_check.filter_factory(conf)(self.app)
        self.assertEqual(0, result.check_config.networks_min)

        body = '{"server": {"networks":[]}}'

        goodurl = '/%s/servers'
        resp = result.__call__.request(goodurl % self.tenant_id, method='POST',
                                       body=body)
        self.assertEqual(self.app, resp)

    def test_boot_beyond_max_networks(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        conf = {'networks_min': '1', 'networks_max': '1', 'enabled': 'true'}

        result = network_count_check.filter_factory(conf)(self.app)
        self.assertEqual(1, result.check_config.networks_min)

        net1 = '{"uuid": "%s"}' % self.pubuuid
        net2 = '{"uuid": "%s"}' % self.adduuid
        body = '{"server": {"networks":[%s, %s]}}' % (net1, net2)

        goodurl = '/%s/servers'
        resp = result.__call__.request(goodurl % self.tenant_id, method='POST',
                                       body=body)
        self.assertTrue(isinstance(resp, webob.exc.HTTPForbidden))
        self.assertTrue('be attached' in str(resp))

    def test_boot_less_than_min_networks(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        conf = {'networks_min': '1', 'networks_max': '2', 'enabled': 'true'}

        result = network_count_check.filter_factory(conf)(self.app)
        self.assertEqual(1, result.check_config.networks_min)
        body = '{"server": {"networks":[]}}'

        goodurl = '/%s/servers'
        resp = result.__call__.request(goodurl % self.tenant_id, method='POST',
                                       body=body)
        self.assertTrue(isinstance(resp, webob.exc.HTTPForbidden))
        self.assertTrue('be attached' in str(resp))

    def test_boot_beyond_max_networks_ok_with_optionals(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        conf = {'networks_min': '1', 'networks_max': '1',
                'optional_nets': self.pubuuid, 'enabled': 'true'}

        result = network_count_check.filter_factory(conf)(self.app)
        self.assertEqual(1, result.check_config.networks_min)

        net1 = '{"uuid": "%s"}' % self.pubuuid
        net2 = '{"uuid": "%s"}' % self.adduuid
        body = '{"server": {"networks":[%s, %s]}}' % (net1, net2)

        goodurl = '/%s/servers'
        resp = result.__call__.request(goodurl % self.tenant_id, method='POST',
                                       body=body)
        self.assertEqual(self.app, resp)

    def test_boot_beyond_max_networks_with_banned(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        conf = {'networks_min': '1', 'networks_max': '2',
                'banned_nets': self.pubuuid, 'enabled': 'true'}

        result = network_count_check.filter_factory(conf)(self.app)
        self.assertEqual(1, result.check_config.networks_min)

        net1 = '{"uuid": "%s"}' % self.pubuuid
        net2 = '{"uuid": "%s"}' % self.adduuid
        body = '{"server": {"networks":[%s, %s]}}' % (net1, net2)

        goodurl = '/%s/servers'
        resp = result.__call__.request(goodurl % self.tenant_id, method='POST',
                                       body=body)
        self.assertTrue(isinstance(resp, webob.exc.HTTPForbidden))
        self.assertTrue('not allowed' in str(resp))

    def test_boot_beyond_max_networks_need_required(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        conf = {'networks_min': '1', 'networks_max': '2',
                'required_nets': self.pubuuid, 'enabled': 'true'}

        result = network_count_check.filter_factory(conf)(self.app)
        self.assertEqual(1, result.check_config.networks_min)

        net1 = '{"uuid": "%s"}' % self.srvuuid
        net2 = '{"uuid": "%s"}' % self.adduuid
        body = '{"server": {"networks":[%s, %s]}}' % (net1, net2)

        goodurl = '/%s/servers'
        resp = result.__call__.request(goodurl % self.tenant_id, method='POST',
                                       body=body)
        self.assertTrue(isinstance(resp, webob.exc.HTTPForbidden))
        self.assertTrue('but missing' in str(resp))

    def test_boot_no_body_returns_app(self):
        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        conf = {'networks_min': '1', 'networks_max': '1',
                'optional_nets': self.pubuuid, 'enabled': 'true'}

        result = network_count_check.filter_factory(conf)(self.app)
        self.assertEqual(1, result.check_config.networks_min)
        body = ''

        goodurl = '/%s/servers'
        resp = result.__call__.request(goodurl % self.tenant_id, method='POST',
                                       body=body)
        self.assertEqual(self.app, resp)

    def test_runtime_overrides(self):
        self.set_reconfigure()
        headers = {'X_WAFFLEHAUS_NETWORKCOUNTCHECK_ENABLED': False}

        m_ctx = self.create_patch(self.ctx_path)
        m_ctx.return_value = self.context
        conf = {'networks_min': '1', 'networks_max': '2',
                'required_nets': self.pubuuid, 'enabled': 'true'}

        result = network_count_check.filter_factory(conf)(self.app)
        self.assertEqual(1, result.check_config.networks_min)

        net1 = '{"uuid": "%s"}' % self.srvuuid
        net2 = '{"uuid": "%s"}' % self.adduuid
        body = '{"server": {"networks":[%s, %s]}}' % (net1, net2)

        goodurl = '/%s/servers'
        resp = result.__call__.request(goodurl % self.tenant_id, method='POST',
                                       body=body)
        self.assertTrue(isinstance(resp, webob.exc.HTTPForbidden))
        self.assertTrue('but missing' in str(resp))

        resp = result.__call__.request(goodurl % self.tenant_id, method='POST',
                                       body=body, headers=headers)
        self.assertFalse(isinstance(resp, webob.exc.HTTPForbidden))
        self.assertFalse('but missing' in str(resp))
