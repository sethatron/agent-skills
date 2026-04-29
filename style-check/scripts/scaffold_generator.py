#!/usr/bin/env python3

import argparse
import os
import sys
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print("[ERROR] jinja2 is required: pip install jinja2", file=sys.stderr)
    sys.exit(1)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "scaffolds"


def parse_coordinate(coordinate: str) -> dict:
    parts = coordinate.split(".")
    if len(parts) < 3:
        print(f"[ERROR] Coordinate must have at least 3 parts (product.subsystem.operation): {coordinate}", file=sys.stderr)
        sys.exit(1)
    return {
        "coordinate": coordinate,
        "product": parts[0],
        "subsystem": parts[1],
        "operation": parts[2],
    }


def render(env, template_name: str, ctx: dict) -> str:
    return env.get_template(template_name).render(**ctx)


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    print(f"  wrote {path}")


def generate_terraform(env, ctx: dict, out: Path):
    sub = ctx["subsystem"]
    op = ctx["operation"]
    layer = out / "terraform" / "layers" / sub / op

    write_file(layer / "main.tf", render(env, "main.tf.j2", ctx))
    write_file(layer / "variables.tf", render(env, "variables.tf.j2", ctx))
    write_file(layer / "outputs.tf", "")

    deploy = layer / "deploy"
    write_file(deploy / "create.sh", render(env, "create-terraform.sh.j2", ctx))
    write_file(deploy / "destroy.sh", render(env, "destroy.sh.j2", ctx))
    write_file(deploy / "luna-config-spec.yaml", render(env, "luna-config-spec.yaml.j2", ctx))
    write_file(deploy / "luna-dependencies.yaml", render(env, "luna-dependencies.yaml.j2", ctx))
    (deploy / "migrations").mkdir(parents=True, exist_ok=True)

    scripts = out / "scripts" / "terraform"
    write_file(scripts / "create.sh", render(env, "scripts-create-terraform.sh.j2", ctx))
    write_file(scripts / "deploy_functions.sh", render(env, "deploy-functions-terraform.sh.j2", ctx))

    write_file(out / "seiji-packaging.yaml", render(env, "seiji-packaging-terraform.yaml.j2", ctx))
    write_file(out / ".terraform-version", "1.1.7\n")

    for f in [deploy / "create.sh", deploy / "destroy.sh", scripts / "create.sh"]:
        f.chmod(0o755)


def generate_helmsman(env, ctx: dict, out: Path):
    deploy = out / "deploy"
    write_file(deploy / "create.sh", render(env, "create-helmsman.sh.j2", ctx))
    write_file(deploy / "destroy.sh", render(env, "destroy-helmsman.sh.j2", ctx))
    write_file(deploy / "deploy_functions.sh", render(env, "deploy-functions-helmsman.sh.j2", ctx))
    write_file(deploy / "luna-config-spec.yaml", render(env, "luna-config-spec.yaml.j2", ctx))
    write_file(deploy / "luna-dependencies.yaml", render(env, "luna-dependencies.yaml.j2", ctx))
    (deploy / "migrations").mkdir(parents=True, exist_ok=True)

    (out / "local-charts").mkdir(parents=True, exist_ok=True)
    (out / "values").mkdir(parents=True, exist_ok=True)

    write_file(out / "desired-state.yaml", render(env, "desired-state.yaml.j2", ctx))
    write_file(out / "desired-state-workspace.yaml", render(env, "desired-state-workspace.yaml.j2", ctx))
    write_file(out / "seiji-packaging.yaml", render(env, "seiji-packaging-helmsman.yaml.j2", ctx))

    for f in [deploy / "create.sh", deploy / "destroy.sh"]:
        f.chmod(0o755)


def main():
    parser = argparse.ArgumentParser(description="Generate a seiji component scaffold")
    parser.add_argument("--coordinate", required=True, help="e.g. nextgen.newsystem.provision")
    parser.add_argument("--type", required=True, choices=["terraform", "helmsman"], dest="component_type")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--dependencies", default="", help="Comma-separated prerequisite coordinates")
    parser.add_argument("--config-vars", default="", help="Comma-separated variable names")

    args = parser.parse_args()

    ctx = parse_coordinate(args.coordinate)
    ctx["dependencies"] = [d.strip() for d in args.dependencies.split(",") if d.strip()]
    ctx["config_vars"] = [v.strip() for v in args.config_vars.split(",") if v.strip()]

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        keep_trailing_newline=True,
    )

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Generating {args.component_type} scaffold for {args.coordinate}")

    if args.component_type == "terraform":
        generate_terraform(env, ctx, out)
    else:
        generate_helmsman(env, ctx, out)

    print("[INFO] Done.")


if __name__ == "__main__":
    main()
