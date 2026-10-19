from pathlib import Path
import os
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scenarios/catalog_try/catalog_try.delete_vms_only.sh'

@pytest.mark.parametrize('listing,code,expected',[('',0,0),('',1,1),('not json',0,1),('{"vm_id":9221}',0,0)])
def test_catalog_try_first_deployment_accepts_verified_empty_inventory_without_deleting_templates(tmp_path,listing,code,expected):
    binary=tmp_path/'bin';binary.mkdir()
    commands={'proxmox_vm.list.to.jsons.sh':f'#!/bin/sh\nprintf \'%s\\n\' \'{listing}\'\nexit {code}\n',
              'proxmox_vm.vm_id.stop_force.to.jsons.sh':'#!/bin/sh\ncat > "$TEST_CALLED"\nexit 99\n',
              'proxmox_vm.vm_id.delete.to.jsons.sh':'#!/bin/sh\ncat > "$TEST_CALLED"\nexit 99\n'}
    for name,content in commands.items():
        path=binary/name;path.write_text(content);path.chmod(0o755)
    env={**os.environ,'PATH':str(binary)+':'+os.environ['PATH'],'HOME':str(tmp_path),'TEST_CALLED':str(tmp_path/'called')}
    result=subprocess.run(['bash',str(SCRIPT)],capture_output=True,text=True,env=env)
    assert (result.returncode==0)==(expected==0),result.stderr
    assert not (tmp_path/'called').exists()
