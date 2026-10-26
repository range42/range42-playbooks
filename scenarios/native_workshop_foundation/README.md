# Prepare reusable workshop templates

Use this optional catalog scenario before creating independent native installation
workshops. Its normal deployment owns two reusable template copies. Participant
runs reserve their own guests and gateway separately; retiring a participant run
does not remove these template copies.

In Deployer UI, open this catalog scenario as a project and save its exact commit.
Choose Deploy and a registered workshop environment. Enter the original source
node and its nested Proxmox and Linux template VMIDs. The destinations and storage
come from the selected environment's approved profile. Review and reserve the
copies, then create the deployment.

To prepare the registered environment's isolated bridges as well, select the
optional bridge preparation setting in Deploy. It requires an approved managed
gateway network and a separately enrolled bounded network module. In Overview,
retain the template request and then review the environment bridge request. The
same full native deployment action prepares both stages. The environment owns
the bridges; each later participant run owns its own gateway and guests.

In Overview, review and reserve physical capacity, request physical acceptance,
then review and retain the preparation request. Run the full deployment action.
The backend uses the existing native attempt and verifies completion directly
against the enrolled node service. Refresh node status in Overview after an
interrupted attempt before resuming the same deployment.

The node administrator must explicitly enroll the optional preparation module for
the exact source generations, configuration fingerprints, destination VMIDs and
storage. The module defaults to disabled. The node copies each approved source,
records the new generation, removes inherited networking and cloud-init login
data, and converts the stopped copy to a template. It never starts a template or
changes an original source. This scenario has no identity-provider dependency.

Preparation reserves 20 GiB of configured RAM, six vCPUs and 192 GiB of virtual
disks plus two cloud-init volumes. The full commitment remains retained during
failure and recovery. Optional bridge preparation installs and verifies its own
firewall before activating the approved bridges. Gateway configuration,
participant installation and exercise isolation must still be qualified before
running a workshop. No participant account or VPN enrollment is performed here.

If a clone reply is lost before its task ID is recorded, the operation stays
uncertain. Do not create a replacement deployment or release its capacity.
Reconcile the original native task as an administrator. Automatic adoption by VM
name, forced cleanup, template deletion and retirement are not provided by this
scenario.
