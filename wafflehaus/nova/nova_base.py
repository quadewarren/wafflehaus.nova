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

from nova import compute

from wafflehaus.base import WafflehausBase


class WafflehausNova(WafflehausBase):

    def _get_compute(self):
        return compute

    def __init__(self, application, conf):
        super(WafflehausNova, self).__init__(application, conf)
        self.compute = self._get_compute()

    def _get_context(self, request):
        """Mock target for testing."""
        context = request.environ.get("nova.context")
        return context

    def _get_instance(self, context, server_id):
        """Mock target for testing."""
        compute_api = self.compute.API()
        instance = compute_api.get(context, server_id, want_objects=True)
        return instance
