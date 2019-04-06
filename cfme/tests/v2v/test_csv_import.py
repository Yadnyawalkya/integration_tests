import tempfile

import fauxfactory
import pytest
from widgetastic.exceptions import WidgetOperationFailed

from cfme.fixtures.v2v_fixtures import infra_mapping_default_data
from cfme.cloud.provider.openstack import OpenStackProvider
from cfme.infrastructure.provider.rhevm import RHEVMProvider
from cfme.infrastructure.provider.virtualcenter import VMwareProvider
from cfme.markers.env_markers.provider import ONE_PER_TYPE
from cfme.markers.env_markers.provider import ONE_PER_VERSION
from cfme.utils.appliance.implementations.ui import navigate_to
from cfme.utils.generators import random_vm_name
from cfme.utils.wait import wait_for

pytestmark = [
    pytest.mark.provider(
        classes=[RHEVMProvider, OpenStackProvider],
        selector=ONE_PER_VERSION,
        scope="module"
    ),
    pytest.mark.provider(
        classes=[VMwareProvider],
        selector=ONE_PER_TYPE,
        fixture_name='source_provider',
        scope="module"
    )
]


@pytest.fixture(scope="function")
def valid_vm(appliance, infra_map):
    """Fixture to get valid vm name from discovery"""
    plan_view = migration_plan(appliance, infra_map, csv=True)
    plan_view.next_btn.click()
    wait_for(lambda: plan_view.vms.is_displayed,
             timeout=60, delay=5, message='Wait for VMs view')
    vm_name = [row.vm_name.text for row in plan_view.vms.table.rows()][0]
    plan_view.cancel_btn.click()
    return vm_name


@pytest.fixture(scope="module")
def infra_map(appliance, v2v_provider_setup):
    """Fixture to create infrastructure mapping"""
    target_provider = [
        v2v_provider_setup.osp_provider
        if v2v_provider_setup.rhv_provider is None
        else v2v_provider_setup.rhv_provider][0]
    infra_mapping_data = infra_mapping_default_data(
        v2v_provider_setup.vmware_provider, target_provider)
    yield appliance.collections.v2v_infra_mappings.create(**infra_mapping_data)
    appliance.collections.v2v_infra_mappings.delete(infra_mapping_data['name'])


def plan_csv_check(appliance, infra_map, error_text, vm_name, headers=None):
    radio_btn = "Import a CSV file with a list of VMs to be migrated"
    plan_obj = appliance.collections.v2v_migration_plans
    view = navigate_to(plan_obj, 'Add')
    view.general.fill({
        "infra_map": infra_map.name,
        "name": fauxfactory.gen_alpha(10),
        "description": fauxfactory.gen_alpha(10),
        "select_vm": radio_btn
    })
    try:
        view.vms.fill({
            'csv_import': True,
            'headers': headers,
            'vm_list': vm_name
        })
    except WidgetOperationFailed:
        pass
    view.vms.table[0][1].widget.click()
    error_msg = view.vms.popover_text.read()
    view.cancel_btn.click()
    return bool(error_msg == error_text)


def test_column_headers(appliance):
    """Test csv with unsupported column header

    Polarion:
        assignee: ytale
        initialEstimate: 1/4h
        casecomponent: V2V
    """
    headers = []
    error_msg = "Error: Required column 'Name' does not exist in the .CSV file"
    plan_csv_check(appliance, infra_map, error_msg, vm_name, headers)
    content = fauxfactory.gen_alpha(10)
    assert import_and_check(appliance, infra_map, error_msg, content=content)
