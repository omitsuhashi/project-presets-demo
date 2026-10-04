# AWS インフラを導入・保守する

共通 Terraform module を固定 Git ref で利用し、**案件固有のファイルは利用側リポジトリで保守します**。
`project-presets-infra` は初回に recipe をコピーするツールです。通常の配置や更新で配布側 CLI / 可変ブランチを実行しません。
対象は Hono / FastAPI を ECS Fargate に配置する、一つのアプリ・一つの環境のデモです。

この手順は開発中の **2.0.0** 用です。まだ公開していないため、まず下記の source checkout から試します。
公開済み 1.0.0 の導入手順は [当時のドキュメント](https://github.com/omitsuhashi/project-presets-demo/blob/infra-aws-container-v1.0.0/docs/infrastructure.md) を参照してください。

## 資材の持ち方

| 資材 | 配布側 | 利用側 |
| --- | --- | --- |
| アプリ preset | 依存・lint・共通設定を継続配布 | 採用版・lock とアプリ固有コードを保守 |
| Terraform module | `infra/modules/` を固定タグで配布 | root の source ref を採用し、更新 PR と plan をレビュー |
| Terraform root・tfvars・backend・provider lock | 初回の見本を提供 | 生成直後から案件所有。自由に編集 |
| Dockerfile・起動サンプル | 初回の見本を提供 | アプリに合わせて保守。配布側は hash 管理しない |
| workflow・`infra/scripts/` | 検証済み recipe を提供 | 案件の通常コードとして保守 |
| recipe の新版 | 新規導入用として公開 | 既存案件へ再同期しない。必要な修正は自分の PR で取り込む |

共通 module の interface は image・port・health path・network・IAM 等です。Hono/FastAPI の違いは Dockerfile とアプリの起動方法が扱います。
案件内の root は module の組み合わせと案件の値を記述します。module source の ref と provider lock は別にレビューします。
`.terraform.lock.hcl` は provider の固定で、Git module は root の ref で固定します。[Terraform module の固定](https://developer.hashicorp.com/terraform/language/modules/configuration#install-a-specific-version-of-the-module)。

## 初回にコピーする

Python 3.12 / uv / Git を用意し、[アプリの導入](install.md) で `typescript-hono` または `python-fastapi` を `--setup` します。
既存アプリは再導入不要です。marker がなければ `--profile typescript-hono` または `--profile python-fastapi` を指定します。

開発版の checkout を指定して、**利用側アプリのルート**から実行します。
`YOUR_OWNER/YOUR_REPO` は利用側の GitHub repository、名前は同じ AWS account/region 内で重複しない 3–20 文字の小文字名です。

```sh
PRESET_CHECKOUT=/absolute/path/to/project-presets-demo
uv run --python 3.12 --project "$PRESET_CHECKOUT/infra" \
  project-presets-infra init --directory "$PWD" \
  --name my-api --repository YOUR_OWNER/YOUR_REPO \
  --module-version 1.0.0
```

開発版の recipe で、公開済み 1.0.0 module を使う例です。`--module-version` は新規導入時の固定参照を選びます。
2.0.0 公開後は同じ Release の wheel から `init` を実行できます。省略時は recipe と同じ module 版を参照します。
公開前の 2.0.0 module ref はまだ取得できないので、公開済み版を明示してください。
既定は東京リージョン `ap-northeast-1` / `main`。変更する場合は `--region` / `--branch` を指定します。
`init` はファイルのコピーだけで、Terraform / Docker / AWS CLI / AWS 認証は不要です。

```text
利用側アプリ/
  Dockerfile                           # 既存なら保持
  .dockerignore                        # 既存なら保持
  infra/
    README.md                          # この案件の操作・保守・復旧手順
    foundation/
      main.tf                          # 共通 module の固定参照
      terraform.tfvars.json
    app/
      main.tf
      terraform.tfvars.json
    scripts/
      infra.py                         # 案件所有の操作入口
      bootstrap.py
      deploy.py
      native.py
  .github/workflows/
    check-infra.yml                    # PR で認証なし検証
    deploy-infra.yml                   # 指定 branch の push / 手動配置
```

新しい所有 marker やインフラ更新 PR workflow は作りません。既存 Terraform root / workflow / script への自動統合もしません。
衝突がある場合は書き込む前に停止します。Dockerfile とアプリの入口が既にあれば保持します。
入口がない場合の Hono `app.ts` / `server.ts`、FastAPI `main.py` は初期サンプルで、以後は案件側のコードです。

## AWS なしで確認する

Terraform 1.16.5、Docker、Python 3.12 を用意します。案件内のスクリプトは Python 標準ライブラリのみで動き、uv や配布パッケージは不要です。

```sh
python3 infra/scripts/infra.py check
python3 infra/scripts/infra.py container-check
```

`check` は両 root の module/provider を取得して validate します。AWS API を呼びません。
`container-check` は linux/amd64 image を build し、設定した環境変数・port・health path で HTTP 応答を検査します。
`secret_arns` がある場合、ローカルは build までで、secret に依存する起動は配置時の ECS/ALB で確認します。

生成ファイルと各 `.terraform.lock.hcl` を commit / push します。state・plan・`.terraform/` は commit しません。
bootstrap 前の deploy workflow は案内だけ表示します。インフラ用の PR 作成権限や updater は不要です。
アプリ preset の更新 PR は独立した仕組みとして継続します。

## AWS の初回準備と通常配置

対象 AWS account の operator 認証と AWS CLI v2 を用意します。次は実際の AWS リソースを作り、料金が発生します。

```sh
python3 infra/scripts/infra.py bootstrap --apply
```

foundation plan/apply → S3 state への移行 → foundation 出力と app backend の設定 → app plan/apply、の順です。
初回は ECR・ALB・cluster 等を作り、image は deploy で配置します。再実行は稼働中の image と既存 backend を保持します。
既存 GitHub OIDC provider は再利用し、この案件が所有する provider は引き続き管理します。
`infra/aws.json` と異なる account での実行は拒否します。

次を commit します。`infra/aws.json` は account・region・deployment role ARN で、secret ではありません。

- `infra/aws.json`、各 `backend.tf.json`。
- app の `foundation.auto.tfvars.json`、更新された foundation の tfvars。
- 両 root の `.terraform.lock.hcl`。

指定 branch へ push すると、案件の workflow が OIDC で CI role を引き受けて配置します。[GitHub OIDC / AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)。
ローカルからの操作は次です。

```sh
python3 infra/scripts/infra.py plan
python3 infra/scripts/infra.py deploy
```

deploy は未適用の foundation 変更があれば停止します。IAM・network・secret ARN の変更は operator が先に bootstrap します。
Docker build → health → ECR push → digest 固定 → Terraform app plan/apply → ECS task revision/image 照合を行います。
Terraform が task definition と service を一貫して管理します。案件 workflow から同じ属性を二重に更新しません。

標準の Terraform コマンドも直接使えます。稼働中 image の digest を明示して保存済み plan をレビュー・適用します。

```sh
terraform -chdir=infra/app init
terraform -chdir=infra/app plan \
  -var='image_uri=ACCOUNT.dkr.ecr.REGION.amazonaws.com/NAME@sha256:DIGEST' \
  -out=deployment.tfplan
terraform -chdir=infra/app apply deployment.tfplan
```

## 案件で更新する

1. 共通 module の採用版を変える PR で、両 root の `source` の固定 ref を変更する。
2. provider 更新が必要なら root の制約と `.terraform.lock.hcl` もレビューする。必要に応じて各 root で `terraform init -upgrade` を使う。
3. 案件の `check` / `container-check` と、bootstrap 済みなら `plan` を実行する。置換・削除の影響を確認する。
4. foundation が変わるなら、その branch で operator が bootstrap し、生成設定を同じ PR に追加する。
5. マージすると案件 workflow が app を配置する。

Dockerfile・workflow・スクリプトも案件側の PR で更新します。recipe の新版に修正例があっても、案件のコードを自動置換しません。
base image の更新や workflow の横断修正は、各案件で取り込む保守負担になります。

## 1.x から所有を移す

既存 state・backend・resource address を保持します。**この移行と module の版上げは別の PR にします。**
CI の配置を一時停止し、同じ checkout の branch で実行します。state を保存・確認し、新しい state で初期化し直さないでください。
開発版からの例:

```sh
uv run --python 3.12 --project "$PRESET_CHECKOUT/infra" \
  project-presets-infra init --directory "$PWD" --adopt
```

`--adopt` は v1 marker と既存の root を確認し、以下だけを変更します。

- 案件所有の scripts、`infra/README.md`、PR check workflow を追加。
- 旧 `infra-tools/v1` を呼ぶ deploy workflow を案件内実行へ置換し、旧 update workflow を削除。
- `infra/.project-infra.json` を削除し、所有権追跡を終了。

Terraform root の内容と固定 module ref、tfvars、backend、AWS 設定、provider lock、Dockerfile、アプリコードは保持します。
新しい `main.tf` を旧 `preset.tf.json` と併置せず、同じ `module.preset` の address を使い続けます。
既存 backend の state key も変更しません。移行だけで AWS apply は実行しません。

独自 workflow や同名 scripts がある場合はコピー前に停止します。その場合は [recipe の元ファイル](../infra/python/project_presets_infra/recipe/) を参考に手動で統合します。
固定 SHA で呼んでいる旧 workflow も手動統合の対象です。差分・認証なし検証・実 plan を確認してから配置を再開します。
公開済み 1.x タグ、wheel、`infra-tools/v1` branch は変更しません。既存案件は移行するまで従来の構成を利用できます。

## 失敗時と対応範囲

bootstrap / S3 state 移行の途中で失敗したら、state・plan を消さず、認証・権限を確認して同じ checkout で再試行します。
Git revert は削除した resource やデータを復元しません。復旧中は配置を止め、必要に応じて S3 state の過去 version と Terraform state 操作を使います。

既定は HTTP、2 public subnet、NAT なしのデモです。HTTPS は同リージョンの ACM ARN を `certificate_arn` に設定し、ドメインを ALB へ向けます。
既存 VPC/private subnet は root から module に渡し、ECR/CloudWatch へ必要な接続を案件側で用意します。
secret の値は tfvars / Docker context に保存せず ARN を渡します。custom KMS key の権限も案件側で設定します。
dev/prod 等を追加するときは名前・root・state key・role を分けます。組織共有の state bucket・OIDC・VPC は所有 root を一つに決めます。
Django / Next.js の起動・DB・migration はこの recipe の対象外です。

## 配布側が公開する

module と初回 recipe は同じ固定タグ `infra-aws-container-vX.Y.Z` で公開します。版の正本は `infra/pyproject.toml` です。
アプリ preset の版を同時に上げる必要はありません。破壊的な interface / resource address の変更には major と移行手順を用意します。
recipe は新規導入用、module は既存案件が採用する依存、という更新契約を守ります。

```sh
terraform fmt -check -recursive infra/modules
for module in infra/modules/*; do
  terraform -chdir="$module" init -backend=false -input=false
  terraform -chdir="$module" validate
  terraform -chdir="$module" test
done
uv run --python 3.12 --project infra python infra/check.py --containers
git diff --check
```

CI 成功後に PR をマージし、未使用の版のタグを公開します。[infra release workflow](../.github/workflows/infra-release.yml) が wheel / sdist / SHA256SUMS を公開します。
2.x は可変 tools branch を作成・更新しません。Git module は同じ固定タグから取得します。公開済みタグ・成果物は差し替えません。
認証なしの Terraform mock / コンテナ検査と、実 AWS の IAM/OIDC・配置確認は別の検証です。
