# YeYing Warehouse Object Capabilities

[简体中文](README_CN.md)

### Purpose

`yeying-warehouse` provides generic, scoped, and auditable object capabilities for listing spaces, inspecting metadata, reading objects, and writing small objects. Warehouse remains the source of truth for object content, permissions, quotas, integrity, and audit records.

### Current Capabilities

- `warehouse.space.list`: list accessible spaces.
- `warehouse.object.list`: list objects.
- `warehouse.object.stat`: inspect object metadata.
- `warehouse.object.read`: read object content.
- `warehouse.object.put`: write objects up to 5 MiB within an authorized path.

### Configuration and Boundaries

The default configuration file is `~/.yeying/skills/warehouse/config.toml`. Callers must provide the Warehouse service URL and a short-lived, revocable Tool credential scoped to the required paths and actions. The Skill does not store caller task or session state, duplicate another product's database or permission system, or expose wallet private keys, user passwords, administrator secrets, or long-lived unrestricted credentials to models or third-party tools.
