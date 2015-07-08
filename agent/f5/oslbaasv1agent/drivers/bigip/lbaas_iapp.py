""" OpenStack LBaaS v1 iApp for BIG-IP """
import pkgutil
# Copyright 2014 F5 Networks Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

PRESENTATION = pkgutil.get_data(
    'f5.oslbaasv1agent',
    'iapps/openstack_lbaas_v1_presentation.txt'
)

IMPLEMENTATION = pkgutil.get_data(
    'f5.oslbaasv1agent',
    'iapps/openstack_lbaas_v1_implementation.txt'
)

IAPP = {
    "name": "f5.lbaas",
    "actions": {
        "definition": {
            "implementation": IMPLEMENTATION,
            "presentation": PRESENTATION
        }
    }
}


def check_install_iapp(bigip):
    """ Ensure the iApp is installed if we should """
    if not bigip.iapp.template_exists('f5.lbaas', 'Common'):
        bigip.iapp.create_template('f5.lbaas', 'Common', IAPP)
