"""Create the AWS foundation and migrate Terraform state with operator credentials."""

import json
import shutil
import subprocess

from .deploy import verify_deployment
from .native import backend, identity, outputs, tf, write_json


def bootstrap(target, apply):
    if not apply:
        raise ValueError("bootstrap creates AWS resources; run bootstrap --apply when operator credentials are ready")
    foundation, app = target / "infra/foundation", target / "infra/app"
    if not shutil.which("aws") or not shutil.which("terraform"):
        raise ValueError("bootstrap needs Terraform >=1.10 and AWS CLI with operator credentials")
    account = identity(target)
    state = json.loads((target / "infra/.project-infra.json").read_text())
    variables = json.loads((foundation / "terraform.tfvars.json").read_text())
    variables["secret_arns"] = json.loads((app / "terraform.tfvars.json").read_text())["secret_arns"]
    tf(foundation, "init", "-input=false", "-migrate-state", "-force-copy")
    listed = subprocess.run(["terraform", f"-chdir={foundation}", "state", "list"], capture_output=True, text=True)
    if listed.returncode and "No state file was found" not in listed.stderr:
        raise ValueError(listed.stderr)
    # Reuse an account's OIDC provider; don't adopt or delete another project's provider.
    if "aws_iam_openid_connect_provider.github" not in listed.stdout and variables["existing_oidc_provider_arn"] is None:
        arn = f"arn:aws:iam::{account}:oidc-provider/token.actions.githubusercontent.com"
        result = subprocess.run(["aws", "iam", "get-open-id-connect-provider", "--open-id-connect-provider-arn", arn], capture_output=True, text=True)
        if result.returncode == 0:
            variables["existing_oidc_provider_arn"] = arn
        elif "NoSuchEntity" not in result.stderr:
            raise ValueError(result.stderr)
    write_json(foundation / "terraform.tfvars.json", variables)
    tf(foundation, "init", "-input=false")
    tf(foundation, "plan", "-input=false", "-out=bootstrap.tfplan")
    # --apply explicitly authorizes applying the displayed, saved plan.
    tf(foundation, "apply", "bootstrap.tfplan")
    values = outputs(foundation)
    if not (foundation / "backend.tf.json").exists():
        backend(foundation, values["state_bucket"], state["region"], "foundation/terraform.tfstate")
        tf(foundation, "init", "-migrate-state", "-force-copy", "-input=false")
    inputs = {key: values[key] for key in ["vpc_id", "subnet_ids", "execution_role_arn", "task_role_arn"]}
    generated = app / "foundation.auto.tfvars.json"
    existing = json.loads(generated.read_text()) if generated.exists() else {}
    write_json(generated, {**existing, **inputs})
    backend(app, values["state_bucket"], state["region"], "app/terraform.tfstate")
    deployment_role = values["deployment_role_arn"]
    tf(app, "init", "-input=false")
    values = outputs(app)
    image = values.get("deployed_image", "")
    tf(app, "plan", "-input=false", f"-var=image_uri={image}", "-out=bootstrap.tfplan")
    tf(app, "apply", "bootstrap.tfplan")
    if image:
        verify_deployment(target, image)
    write_json(target / "infra/aws.json", {"account": account, "region": state["region"], "role": deployment_role})
    print("Bootstrap complete. Commit infra/*.json, root calls, native provider locks and workflows. Never commit state/plans or AWS credentials.")
