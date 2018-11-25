"""Test to validate End-to-End migrations- functional testing."""
import fauxfactory
import pytest

from cfme.fixtures.provider import (dual_network_template, dual_disk_template,
 dportgroup_template, win7_template, win10_template, win2016_template, rhel69_template,
 win2012_template, ubuntu16_template, rhel7_minimal)
from cfme.infrastructure.provider.rhevm import RHEVMProvider
from cfme.infrastructure.provider.virtualcenter import VMwareProvider
from cfme.markers.env_markers.provider import ONE_PER_VERSION
from cfme.utils.appliance.implementations.ui import navigate_to, navigator
from cfme.utils.log import logger
from cfme.utils.wait import wait_for

pytestmark = [
    pytest.mark.ignore_stream('5.8'),
    pytest.mark.provider(
        classes=[RHEVMProvider],
        selector=ONE_PER_VERSION,
        required_flags=['v2v']
    ),
    pytest.mark.provider(
        classes=[VMwareProvider],
        selector=ONE_PER_VERSION,
        fixture_name='second_provider',
        required_flags=['v2v']
    )
]


def get_migrated_vm_obj(src_vm_obj, target_provider):
    """Returns the migrated_vm obj from target_provider."""
    collection = target_provider.appliance.provider_based_collection(target_provider)
    migrated_vm = collection.instantiate(src_vm_obj.name, target_provider)
    return migrated_vm


ACTIONS = {
    'evmserver_reboot': 'restart_evm_rude',
    'appliance_reboot': 'reboot'
}


@pytest.mark.parametrize('param', ACTIONS.keys(), ids=[item for item in ACTIONS.keys()])
@pytest.mark.parametrize('form_data_vm_obj_single_datastore', [['nfs', 'nfs', rhel7_minimal]],
                         indirect=['form_data_vm_obj_single_datastore'])
def test_migration_restart(request, appliance, v2v_providers, host_creds, conversion_tags, param,
                           form_data_vm_obj_single_datastore):
    """Test migration by restarting system in middle of the process"""

    infrastructure_mapping_collection = appliance.collections.v2v_mappings
    mapping = infrastructure_mapping_collection.create(form_data_vm_obj_single_datastore.form_data)

    @request.addfinalizer
    def _cleanup():
        infrastructure_mapping_collection.delete(mapping)

    # vm_obj is a list, with only 1 VM object, hence [0]
    src_vm_obj = form_data_vm_obj_single_datastore.vm_list[0]

    migration_plan_collection = appliance.collections.v2v_plans
    migration_plan = migration_plan_collection.create(
        name="plan_{}".format(fauxfactory.gen_alphanumeric()), description="desc_{}"
        .format(fauxfactory.gen_alphanumeric()), infra_map=mapping.name,
        vm_list=form_data_vm_obj_single_datastore.vm_list, start_migration=True)

    # explicit wait for spinner of in-progress status card before reboot
    view = appliance.browser.create_view(
        navigator.get_class(migration_plan_collection, 'All').VIEW.pick())
    wait_for(func=view.progress_card.is_plan_started, func_args=[migration_plan.name],
        message="migration plan is starting, be patient please", delay=5, num_sec=150,
        handle_exception=True)

    def _system_reboot():
        # function to reboot system when migrated percentage greater than 40%
        ds_percent = view.progress_card.get_progress_percent(migration_plan.name)["datastores"]
        print ds_percent
        if int(ds_percent) > 40:
            getattr(appliance, ACTIONS[param])()
            wait_for(func=appliance.wait_for_web_ui, delay=10, num_sec=1200,
                     message="{} restarted, be patient please".format(param))
            print True
            return True
        else:
            print False
            return False

### store value of earlier size and just check if size has increased

    # wait until system restarts
    wait_for(func=_system_reboot, message="migration plan is in progress, be patient please",
     delay=5, num_sec=1800)

    import ipdb;ipdb.set_trace()
    # navigate_to(migration_plan_collection, 'All')

    # wait until plan is in progress
    wait_for(func=view.plan_in_progress, func_args=[migration_plan.name],
        message="migration plan is in progress, be patient please",
        delay=5, num_sec=1800)

    view.switch_to("Completed Plans")
    view.wait_displayed()
    migration_plan_collection.find_completed_plan(migration_plan)
    logger.info("For plan %s, migration status after completion: %s, total time elapsed: %s",
        migration_plan.name, view.migration_plans_completed_list.get_vm_count_in_plan(
            migration_plan.name), view.migration_plans_completed_list.get_clock(
            migration_plan.name))
    # validate MAC address matches between source and target VMs
    assert view.migration_plans_completed_list.is_plan_succeeded(migration_plan.name)
    migrated_vm = get_migrated_vm_obj(src_vm_obj, v2v_providers.rhv_provider)
    assert src_vm_obj.mac_address == migrated_vm.mac_address
