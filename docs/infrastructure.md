# AWS インフラの導入・配布更新・適用

アプリの preset の上に、固定タグの Terraform module を参照するインフラを追加します。最初の構成は **Hono / Node.js と FastAPI / Python の HTTP サービスを ECS Fargate に配置するデモ**です。AWS アカウント・認証は後から用意できます。`init` はローカルのファイルを生成するだけです。

## 導入する

Node.js 24 / npm、Python 3.12 / uv、Git を用意し、[アプリの導入](install.md) で `typescript-hono` または `python-fastapi` を `--setup` します。アプリを導入済みなら再実行は不要です。

```sh
# TypeScript の新規プロジェクトで実行する場合
npx --yes --allow-remote=root --ignore-scripts \
  https://github.com/omitsuhashi/project-presets-demo/releases/download/v2.1.0/project-presets-demo-2.1.0.tgz \
  typescript-hono --setup

# Python の新規プロジェクトで実行する場合
uvx --python 3.12 \
  --from https://github.com/omitsuhashi/project-presets-demo/releases/download/v2.1.0/project_presets_demo-2.1.0-py3-none-any.whl \
  project-presets-python python-fastapi --setup
```

次はどちらの言語でも同じ入口です。`my-api` は AWS 内で使う 3–20 文字の小文字名、`YOUR_OWNER/YOUR_REPO` は**利用側**の GitHub repository に置き換えます。同じ AWS アカウント・リージョン内では異なる名前にしてください。

```sh
# このターミナル内だけで使う関数。パッケージの事前インストールは不要。
infra_preset() {
  uvx --python 3.12 \
    --from https://github.com/omitsuhashi/project-presets-demo/releases/download/infra-aws-container-v1.0.0/project_presets_infra-1.0.0-py3-none-any.whl \
    project-presets-infra "$@"
}

infra_preset init --name my-api --repository YOUR_OWNER/YOUR_REPO
```

`.project-preset.json` から Profile を読みます。既存の独自アプリで marker がなければ `--profile typescript-hono` / `--profile python-fastapi` を指定できます。既定は `ap-northeast-1` / `main`、変更する場合は `--region` / `--branch` を指定します。

生成結果:

| ファイル | 役割・管理範囲 |
| --- | --- |
| `infra/foundation/preset.tf.json` | VPC・subnet・S3 state・GitHub OIDC・IAM の固定 module 参照 |
| `infra/app/preset.tf.json` | ECR・ECS・ALB・ログの固定 module 参照 |
| 各 `terraform.tfvars.json` | 利用側の名前・リージョン・ポート・環境変数・CPU・メモリ・TLS 等 |
| `infra/.project-infra.json` | インフラの版、管理する provider pin、生成 Dockerfile の hash |
| `Dockerfile` / `.dockerignore` | 既存なら保持。新規生成したものだけ更新対象にする |
| `.github/workflows/deploy-infra.yml` | 既定 branch の push / 手動実行で配置 |
| `.github/workflows/update-infra.yml` | 月曜 11:45 日本時間 / 手動実行で更新 PR |

アプリの入口がない場合は、Hono の `app.ts` / `server.ts`、FastAPI の `main.py` と `/health` を追加します。このコードは初期サンプルで、その後は利用側が保守します。既存コードは上書きしません。独自アプリは Dockerfile の起動コマンドと `container_port` / `health_check_path` を合わせてください。生成先の Terraform / workflow が既に存在する場合は、統合が必要なファイルを示して停止します。

初期化の時点では AWS CLI / Terraform / Docker は不要です。後から以下を実行できます。

```sh
# Terraform 1.16.5 を使う。module/provider の取得はするが AWS API を呼ばない。
infra_preset check

# Docker が使える場合。linux/amd64 イメージを build し、非 root 実行で /health を確認。
infra_preset container-check
```

生成ファイルと `check` が作った各 `.terraform.lock.hcl` を commit / push します。state・plan・`.terraform/` は生成した `.gitignore` で除外します。AWS bootstrap 前の deploy workflow は案内を表示して終了します。更新 workflow は AWS なしで設定・コンテナを検証して PR を作れます。Actions の PR 作成には、Settings → Actions → General → **Allow GitHub Actions to create and approve pull requests** を有効にします。

## AWS を用意した後に初回の土台を作る

ここからは AWS リソースを作成し、ECS Fargate・ALB・ECR・CloudWatch 等の料金が発生します。今回は認証設定と実 AWS 検証を後回しにしています。利用時には Terraform 1.16.5、AWS CLI v2、Docker と対象アカウントの operator 認証を用意します。長期 AWS キーをリポジトリに保存する必要はありません。

```sh
infra_preset bootstrap --apply
```

`--apply` が AWS 作成を明示的に許可します。foundation / app の plan を表示し、その保存済み plan を適用します。初回はアプリのイメージをまだ配置せず、ECR・ALB・cluster 等を用意します。既存の配置後に再実行した場合は、state の稼働イメージを引き継ぎます。

foundation のローカル state で state bucket を作った後、自動的に S3 backend に移します。S3 は versioning・暗号化・public block・TLS 強制・ネイティブの lockfile を使います。foundation と app は別の state key です。DynamoDB の新規 lock table は不要です。[Terraform S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3)。

bootstrap 後に commit するもの:

- `infra/aws.json`: account ID・region・deployment role ARN。認証情報ではありません。
- 各 `backend.tf.json`、app の `foundation.auto.tfvars.json`、foundation の更新済み `terraform.tfvars.json`。
- 各 `.terraform.lock.hcl`、module 参照、marker と workflow。

既存の GitHub OIDC provider があるアカウントでは再利用し、他案件の provider を Terraform 管理に取り込みません。trust は指定した利用 repository と branch に限定します。通常の CI role はアプリ用リソースの変更と foundation の読み取り / plan に使い、IAM の権限変更・VPC 作成・foundation state 本体の書き込みは許可しません。[GitHub OIDC / AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)。

途中で失敗した場合は state・plan を消さず、認証・権限・ログを確認して同じ checkout の bootstrap を再実行します。state の S3 移行失敗も同じ checkout で再試行します。別ディレクトリから初期化し直すと、管理済みリソースを別 state として作ろうとするため避けます。CLI は保存済み `infra/aws.json` と異なるアカウントの認証での実行を拒否します。

## 通常のデプロイ

bootstrap の生成ファイルを既定 branch に push すると、OIDC で CI role を引き受けて配置します。ローカルの認証から同じ処理を実行する場合は:

```sh
infra_preset deploy
```

foundation に未適用の変更があれば停止します。通常の流れは Docker build → ローカル `/health` → ECR push → ECR の digest を取得 → digest を指定した Terraform plan / apply です。ECS task definition と service は Terraform が一貫して管理します。ECR のタグは immutable、ECS は安定するまで待ち、deployment circuit breaker で失敗した配置を戻します。適用後に ECS が実際に使う image も照合し、rollback した場合は成功として扱いません。

TypeScript の Docker build は利用側の `packageManager` に固定した pnpm と `pnpm-lock.yaml`、Python は `uv.lock` を使います。Python の実行イメージには開発用 preset / Ruff を入れません。AWS ECR の login token は一時 Docker config と標準入力で渡し、終了時にその config を削除します。

このデモは 2 public subnet を持つ VPC と、ALB からだけアプリポートへの ingress を許す Fargate task を使います。NAT を作らないデモ構成です。商用 AWS リージョン、linux/amd64、Hono / FastAPI が初期対象で、Django / Next.js の起動・DB・migration はこのデモに含みません。ECR のイメージは自動削除せず、ロールバック用に保持するため、運用時には保持方針を決めてください。

既定は HTTP です。HTTPS を使う場合は `infra/app/terraform.tfvars.json` の `certificate_arn` に同じリージョンの ACM 証明書 ARN を設定し、証明書のドメインを ALB へ向けます。HTTP は HTTPS に redirect します。private subnet が必要な場合は service module に既存 VPC / private subnet を渡し `assign_public_ip=false` にし、ECR / CloudWatch への VPC endpoint または NAT を利用側で用意します。foundation はデモ用ネットワークなので、既存ネットワークを使う構成は別の root で統合してください。

secret の値は tfvars / Docker context に書かず、`secret_arns` に Secrets Manager / SSM の ARN を渡します。追加・削除時は execution role の権限も変わるため bootstrap を operator で適用します。カスタム KMS key を使う secret は利用側で `kms:Decrypt` を付与します。

## 配布側が更新する

インフラの版は `infra/pyproject.toml` だけで管理し、タグは **`infra-aws-container-vX.Y.Z`** にします。アプリ用 `v2.1.0` や TypeScript / Python の版を上げる必要はありません。

1. module、CLI、Docker template、reusable workflow を同じ PR で変更する。AWS provider は CLI の `PROVIDER` と module の制約を揃える。Terraform の採用版は workflow と本手順に記録する。
2. 互換修正は patch、追加は minor、既存 resource address / 入力の削除・変更や破壊的な再作成は major と移行手順を用意する。lint / framework の更新はアプリ側の配布手順を使う。
3. `uv version --project infra X.Y.Z --no-sync` でインフラだけ版を変更し、変更説明と公開 URL を更新する。
4. 以下の検証と GitHub CI を通し、PR をマージする。

```sh
terraform fmt -check -recursive infra/modules
for module in infra/modules/*; do
  terraform -chdir="$module" init -backend=false -input=false
  terraform -chdir="$module" validate
  terraform -chdir="$module" test
done
uv run --project infra python infra/check.py --containers
git diff --check
```

Terraform の mock は AWS API を使わず、実 provider の schema に対して plan を検証します。CLI は wheel の一時実行、両 Profile、追加 resource / 変数の保持、管理箇所の競合、両コンテナの HTTP 応答を検証します。IAM policy の実際の許可判定、AWS quota / AZ / service の動作は AWS 認証後の検証対象です。[Terraform mock tests](https://developer.hashicorp.com/terraform/language/tests/mocking)。

```sh
# マージ後 main の CI 成功を確認して、未使用の版を公開する例
git switch main
git pull --ff-only
git tag infra-aws-container-v1.0.1
git push origin infra-aws-container-v1.0.1
```

[infra release workflow](../.github/workflows/infra-release.yml) はインフラの検証を再実行し、wheel / sdist / `SHA256SUMS` を独立 Release に公開します。module は同じ Git タグから取得します。公開済みタグや artifact は差し替えません。インフラ Release をアプリ側の「latest」にしません。

公開成功後、互換ツール用の **`infra-tools/v1` branch** をその commit に進めます。利用 workflow はこの branch を参照するため、deployment / update CLI の互換修正も追従します。Terraform module と Dockerfile / provider の更新は固定タグを変更する PR でレビューします。ツール用 branch は可変であり、配布 repository の workflow / CLI を実行する信頼境界です。全コードを immutable に固定したい利用側は workflow の `@infra-tools/v1` を検証済み commit SHA に変え、ツールの更新を別 PR で保守します。次の major は別 branch を使い、既存 major の branch を切り替えません。

## 利用側が更新を当てる

毎週の update workflow は同じ major の安定した **infra タグだけ**を選びます。module source、管理 provider pin、生成時から管理している Dockerfile / `.dockerignore`、marker、provider lock を更新し、設定とコンテナを検証して PR にします。bootstrap 済みなら両 state の実 plan も実行します。この job は apply しません。既存の同じ版の更新 branch があれば、利用側のレビューや編集を上書きせず保持します。

GitHub の `GITHUB_TOKEN` で作成した PR は他の PR workflow を自動起動しないため、作成前に上記の検証を行います。利用側の追加チェックはマージ前に手動実行してください。差分がなければ PR は作りません。

利用側が追加した `terraform.tfvars.json` の値、他の module / resource / output、独自 Dockerfile は保持します。同じ `preset.tf.json` の中でも、管理する `module.preset.source` と AWS provider pin だけを変更します。管理箇所や生成 Dockerfile を利用側で変更 / 削除した場合は、書き換える前に停止します。変更を upstream へ取り込むか、利用側で独自構成へ移行します。Git の競合とは別に、この所有範囲のチェックを行います。

手動更新では**採用する新版の wheel**から CLI を実行します。旧 CLI に新版の module だけを選ばせると provider / Docker template / tooling が揃わないため拒否します。

```sh
# 例: 1.0.1 の公開後に、その新版 URL で実行する
uvx --python 3.12 \
  --from https://github.com/omitsuhashi/project-presets-demo/releases/download/infra-aws-container-v1.0.1/project_presets_infra-1.0.1-py3-none-any.whl \
  project-presets-infra update --version 1.0.1
```

`check` / `container-check` と、AWS bootstrap 後なら `plan` を実行します。`plan` は state に記録した稼働中の image digest を引き継ぎます。Terraform の `image_uri` には既定値を設けていないため、通常の native plan でもイメージの入力を省くと勝手に初期値へ戻りません。

PR で foundation の変更があれば、更新 branch を checkout して新版 CLI の `bootstrap --apply` を operator で実行し、生成設定を同じ PR に追加します。IAM・ネットワークは広い CI role で自動適用しません。その後マージすると deploy workflow が新しい module / Dockerfile で image を build し、app を適用します。foundation の未適用変更は CI が検出して停止します。

ロールバックは旧 module / Dockerfile の commit に revert し、plan をレビューしてから配置します。Git revert は resource の削除やデータを復元しません。以前の image を再配置する場合は、その ECR digest を `image_uri` に明示して native Terraform plan / apply します。state 破損の復旧は S3 の過去 version と Terraform の state 操作で行い、復旧中は deployment workflow を停止して並行 apply を避けます。
