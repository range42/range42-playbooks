# Prepare reusable templates

Open this scenario from Catalog, save the project revision, then choose Deploy.
Select an environment with an approved resource profile. Give the preparation a
name and supply the original source node and one source VMID for each named
template. Template roles, destination VMIDs, storage and hardware come from the
profile; the recipe does not assume any particular installed product.

Review and reserve the copies, then create the deployment. In Overview, reserve
and physically accept capacity, retain the preparation request, and run the full
native action. Progress and reconciliation use the existing deployment attempt,
allocation and capacity records. No participant accounts are created.

The optional bounded node module must be explicitly enrolled for the same source
generations, configuration revisions, output IDs and hardware. It supports one
to sixteen templates, each with one or two SCSI disks and cloud-init. Current
preparation requires stopped sources with CPU host and the guest agent enabled.
Unsupported source shapes require another implementation; they are not guessed.

An environment may also opt into its separately enrolled isolated-bridge provider
and management network. This is optional; normal native SDN scenarios keep their
existing network workflow. VPN and identity providers are separate integrations.

The full capacity hold remains during interrupted or uncertain operations.
Reconcile the original request before resuming; never replace a lost clone with
a new deployment to clear its ownership. Template retirement is not supplied by
this recipe.
