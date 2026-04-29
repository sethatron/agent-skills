# Config Spec Reference (luna-config-spec.yaml)

Defines the configuration variables a Seiji component expects, their types, defaults, and how they flow into Terraform and SSM.

## Schema

Top-level key is `config`, containing component keys mapping to variable definitions:

```yaml
config:
  _:
    # Global variables (shared across components)
    admin_cidrs:
      description: "Known-trusted CIDRs for k8s control plane, S3, etc."
      required: true
      tfvar: true
      type: list

  nextgen.eks:
    # Component-specific variables
    ...
```

- `config._` holds global variables available to all components
- `config.{coordinate}` holds variables scoped to a specific component (e.g., `nextgen.eks`, `jupyter`, `xrbm`)

## Variable Fields

From `SeijiConfigSpecVariable` in `seiji_config/models.py`:

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | enum | yes | - | `str`, `int`, `bool`, `list`, `map` |
| `required` | bool | yes | - | Must be present in luna-config.yaml |
| `tfvar` | bool | no | `false` | Include in generated `.auto.tfvars` |
| `default` | any | no | - | Default value (must match declared type) |
| `description` | str | no | - | Human-readable description |
| `secret` | bool | no | `false` | Stored in secrets path instead of config path |

## Real Examples

### Global variables (from onyx provision):

```yaml
config:
  _:
    admin_cidrs:
      description: "Known-trusted CIDRs which will be able to access the k8s control plane, S3 buckets, and other resources."
      required: true
      tfvar: true
      type: list
    workspaces:
      description: "A list of workspaces that will run in this environment."
      required: false
      tfvar: true
      type: list
    dr_label:
      description: "The Seiji label for the deployment in the DR region."
      required: false
      tfvar: true
      type: str
```

### Component-scoped variables (from sample):

```yaml
config:
  jupyter:
    notebook_eks_worker_ance_type:
      type: "str"
      required: true
      default: "t3.large"
      tfvar: true

  ldps:
    incoming_sqs_queue_delay_seconds:
      type: "int"
      required: false
      default: 15
      tfvar: false

    services_to_monitor:
      type: "list"
      required: true
      tfvar: true

  xrbm:
    enable:
      description: A required true or false value to install XRBM
      required: true
      tfvar: false
      type: bool
```

## Config Flow

```
luna-config-spec.yaml
    |
    v
seiji config generate tfvars --spec-path deploy/luna-config-spec.yaml
    |
    |  reads variable definitions from spec
    |  pulls current values from SSM Parameter Store
    |  writes .auto.tfvars files
    v
*.auto.tfvars  -->  terraform apply
```

Only variables with `tfvar: true` are included in the generated tfvars.

## SSM Path Convention

Variables are stored in SSM under paths determined by their component coordinate and `secret` flag:

**Config variables:**
```
/${LABEL}/config/{component}/{variable}
```

**Secret variables:**
```
/${LABEL}/secrets/{component}/{variable}
```

**Global variables** (component = `_`):
```
/${LABEL}/config/_/{variable}
```

List and map types get a `/json` suffix in SSM:
```
/${LABEL}/config/_/workspaces/json
/${LABEL}/config/_/admin_cidrs/json
```

## Flat Variable Mapping

From the `flat_variable_default_map()` method in the Pydantic model:

```python
for component, variables in self.config.items():
    for name, var in variables.items():
        variable_suffix = f"{component}/{name}"
        if var.secret:
            variable_name = f"secrets/{variable_suffix}"
        else:
            variable_name = f"config/{variable_suffix}"
        output[variable_name] = var.default
```

This produces a flat map like:
```
config/_/admin_cidrs -> None
config/_/workspaces -> None
config/jupyter/notebook_eks_worker_ance_type -> "t3.large"
secrets/xrbm/api_key -> None
```

## Writing Computed Values

Use `seiji config write` to push computed values back to SSM:

```bash
cat > "$temp_config_file" << EOF
variables:
  _:
    metastore_id: "${existing_metastore}"
EOF

seiji config write --config-path "$temp_config_file" --auto-approve
```

This is used by infrastructure layers that discover values at deploy time (e.g., auto-detected Databricks metastore IDs) and need to persist them for downstream components.
