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
import webob.dec
from webob import exc

from wafflehaus.nova.networking import networking_base as net_base

from oslo.serialization import jsonutils
from oslo_utils import uuidutils

from nova.compute import utils as compute_utils


def _get_body(request, json_property):
    """Returns body serialized from JSON."""
    body = jsonutils.loads(request.body)
    body = body[json_property]
    return body


def check_required_networks(networks, required_networks):
    """Verifies required networks are present."""
    if required_networks:
        msg = "Networks (%s) required but missing"
        msg_networks = ",".join(required_networks)
        if required_networks.intersection(networks) != required_networks:
            return msg % msg_networks
    return ""


def check_banned_networks(networks, banned_networks):
    """Verifies banned networks are not present."""
    if banned_networks:
        msg = "Networks (%s) not allowed"
        msg_networks = ",".join(banned_networks)
        if banned_networks.intersection(networks) != set():
            return msg % msg_networks
    return ""


def check_network_count(networks, min_nets, max_nets, existing_nets,
                        optional_nets, count_optional_nets):
    """Verifies correct number of isolated networks."""
    if not min_nets:
        msg = "At most %i isolated network(s) can be attached"
        msg_network_count = (max_nets)
    elif min_nets == max_nets:
        msg = "Exactly %i isolated network(s) must be attached"
        msg_network_count = (min_nets)
    else:
        msg = "Only %i to %i isolated network(s) can be attached"
        msg_network_count = (min_nets, max_nets)

    if existing_nets:
        isolated_nets = networks | existing_nets
    else:
        isolated_nets = networks

    if not count_optional_nets:
        isolated_nets = isolated_nets - optional_nets

    if ((min_nets and len(isolated_nets) < min_nets) or
            len(isolated_nets) > max_nets):
        return msg % msg_network_count
    return ""


class NetworkCountConfig(object):
    def __init__(self, local_config):
        self.banned_networks = local_config.get("banned_nets", "")
        self.banned_networks = set([n.strip()
                                   for n in self.banned_networks.split()])
        self.required_networks = local_config.get("required_nets", "")
        self.required_networks = set([n.strip()
                                     for n in self.required_networks.split()])
        self.optional_networks = local_config.get("optional_nets", "")
        self.optional_networks = set([n.strip()
                                     for n in self.optional_networks.split()])
        self.networks_min = int(local_config.get("networks_min", "1"))
        self.networks_max = int(local_config.get("networks_max", "1"))
        self.count_optional_nets = bool(local_config.get(
            "count_optional_nets", False))
        self.strict_boot_check = bool(local_config.get(
            "strict_boot_check", False))


class BootNetworkCountCheck(object):
    """Verifies networks on server boot."""
    def __init__(self, check_config, log):
        self.check_config = check_config
        self.log = log

    @staticmethod
    def _is_server_boot_request(pathparts, req, projectid):
        """Determines if this is a cloud server boot request based on URL."""
        pathparts = set(pathparts)
        bootcheck = set([projectid, "servers"])
        if pathparts != bootcheck:
            return False
        if not req.body or len(req.body) == 0:
            return False
        return True

    @staticmethod
    def _get_networks(body):
        """Extract networks from body."""
        networks = body.get("networks")
        if networks is None:
            return None
        return [n["uuid"] for n in networks if "uuid" in n]

    def _get_networks_from_request(self, req):
        """Returns networks given in server boot request."""
        networks = self._get_networks(_get_body(req, "server"))
        if networks is None:
            return None
        if not networks:
            return set()
        return set(networks)

    def check_networks(self, req):
        """Checks required/banned/count of networks."""
        cfg = self.check_config
        networks = self._get_networks_from_request(req)

        if cfg.strict_boot_check and networks is None:
            networks = set()

        if networks is None:
            return ""

        msg = check_required_networks(networks, cfg.required_networks)
        if msg:
            return msg
        msg = check_banned_networks(networks, cfg.banned_networks)
        if msg:
            return msg
        return check_network_count(networks, cfg.networks_min,
                                   cfg.networks_max,
                                   None, cfg.optional_networks,
                                   cfg.count_optional_nets)


class AttachNetworkCountCheck(object):
    """Verifies networks on network/vif attach request."""
    def __init__(self, check_config, log, get_instance):
        self.check_config = check_config
        self.log = log
        self.get_instance = get_instance

    @staticmethod
    def _is_attach_network_request(pathparts, projectid):
        if (len(pathparts) != 4 or
                pathparts[0] != projectid or
                pathparts[1] != "servers" or
                pathparts[3] != "os-virtual-interfacesv2"):
            return False

        return uuidutils.is_uuid_like(pathparts[2])

    def _get_existing_networks(self, context, server_id):
        """Returns networks a server is already connected to."""
        instance = self.get_instance(context, server_id)
        nw_info = compute_utils.get_nw_info_for_instance(instance)

        networks = []
        for vif in nw_info:
            networks.append(vif["network"]["id"])

        if not networks:
            return set()
        return set(networks)

    def _get_attaching_network(self, request):
        """Extract network to be added from request."""
        if not request.body or len(request.body) == 0:
            return None
        body = _get_body(request, "virtual_interface")
        if not body or 'network_id' not in body:
            return None
        return body['network_id']

    def check_networks(self, context, request, server_id):
        """Checks banned/count of networks."""
        cfg = self.check_config
        networks = set([self._get_attaching_network(request)])
        if None in networks:
            networks.remove(None)
        if not len(networks):
            return ''
        existing_networks = self._get_existing_networks(context, server_id)

        # Note: don't need to check required nets on attach
        # Min as 0 since only attach 1 at a time; in case 2 or more under min
        msg = check_banned_networks(networks, cfg.banned_networks)
        if msg:
            return msg
        return check_network_count(networks, None, cfg.networks_max,
                                   existing_networks, cfg.optional_networks,
                                   cfg.count_optional_nets)


class NetworkCountCheck(net_base.WafflehausNovaNetworking):
    def __init__(self, app, conf):
        super(NetworkCountCheck, self).__init__(app, conf)
        self.log.name = conf.get('log_name', __name__)
        self.log.info('Starting wafflehaus network count check middleware')
        self.check_config = NetworkCountConfig(conf)

    @webob.dec.wsgify
    def __call__(self, req, **local_config):
        super(NetworkCountCheck, self).__call__(req)
        if not self.enabled:
            return self.app

        verb = req.method
        if verb != "POST":
            return self.app

        context = self._get_context(req)
        if not context:
            return self.app

        projectid = context.project_id
        path = req.environ.get("PATH_INFO")
        if path is None:
            return self.app

        pathparts = [part for part in path.split("/") if part]
        msg = ""
        if AttachNetworkCountCheck._is_attach_network_request(pathparts,
                                                              projectid):
            check = AttachNetworkCountCheck(self.check_config, self.log,
                                            self._get_instance)
            msg = check.check_networks(context, req, pathparts[2])
        elif BootNetworkCountCheck._is_server_boot_request(pathparts, req,
                                                           projectid):
            check = BootNetworkCountCheck(self.check_config, self.log)
            msg = check.check_networks(req)
        if msg:
            return exc.HTTPForbidden(msg)

        return self.app


def filter_factory(global_conf, **local_conf):
    """Returns a WSGI filter app for use with paste.deploy."""
    conf = global_conf.copy()
    conf.update(local_conf)

    def net_count_check(app):
        """Returns the app for paste.deploy."""
        return NetworkCountCheck(app, conf)
    return net_count_check
