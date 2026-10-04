# この案件の AWS インフラ

この recipe は project-presets-infra __RECIPE_VERSION__ で初回生成しました。
**生成後のファイルは、この案件で保守します。** 生成ツールは更新や配置には使いません。

| 資材 | 所有・更新方法 |
| --- | --- |
| Terraform root、tfvars、backend、provider lock | 案件所有。変更を PR と plan でレビュー |
| 共通 Terraform module | root の固定 Git ref で利用。参照版を変更して plan を確認 |
| Dockerfile、アプリの入口 | 案件所有。base image・起動方法を自分の PR で更新 |
| `infra/scripts/`、GitHub Actions workflow | 案件所有。通常のコードとして変更・検証 |
| recipe の新版 | 新規導入用の見本。既存案件へ自動同期しない |

`infra/foundation` はネットワーク・IAM・state 保存先、`infra/app` は ECR・ALB・ECS を管理します。
初回は一つのアプリ・一つの環境です。別環境は root、名前、backend key、role を分け、同じ resource を二つの state で管理しません。

## AWS を使う前に

Terraform 1.16.5、Docker、Python 3.12 を用意します。スクリプトは Python 標準ライブラリだけで動きます。

```sh
python3 infra/scripts/infra.py check
python3 infra/scripts/infra.py container-check
```

port、health path、環境変数、CPU、memory、TLS は `infra/app/terraform.tfvars.json` で設定します。
独自アプリの Dockerfile・起動コマンドも合わせます。既定は HTTP、public subnet の Fargate デモです。
AWS secret の値はファイルへ保存せず、`secret_arns` に Secrets Manager / SSM の ARN を指定します。
secret がある場合、ローカル検査は build までで、起動時の health は ECS/ALB で確認します。

生成ファイルと両 root の `.terraform.lock.hcl` を commit します。state・plan・`.terraform/` は commit しません。
PR の check workflow は AWS 認証なしで実行できます。bootstrap 前の deploy workflow は案内だけ表示します。

## 初回 AWS 準備と復旧

対象 AWS アカウントの operator 認証と AWS CLI v2 を用意します。次は AWS リソースを作り、料金が発生します。

```sh
python3 infra/scripts/infra.py bootstrap --apply
```

foundation の保存済み plan を適用 → S3 state へ移行 → foundation の出力と app backend を設定 → app の保存済み plan を適用、の順です。
初回は ECR・ALB・cluster 等を作り、アプリ image は次の deploy で配置します。再実行は稼働中の image を維持します。
既存 backend は保持します。既存 OIDC provider は再利用し、この案件が管理する provider はそのまま管理します。

途中で失敗したら state や plan を消さず、認証・権限を確認して**同じ checkout**で再実行します。
S3 移行失敗も同じ checkout で再試行します。別ディレクトリから新しい state を作って再初期化しません。
保存済み `infra/aws.json` と異なる account の認証は拒否します。

`infra/aws.json`（account・region・role ARN。secret ではない）、各 backend、`foundation.auto.tfvars.json`、tfvars、provider lock を commit します。
既定 branch へ push すると、この案件の workflow が GitHub OIDC で配置します。長期 AWS キーを repo に保存する必要はありません。

## 配置と更新

```sh
python3 infra/scripts/infra.py plan
python3 infra/scripts/infra.py deploy
```

deploy は foundation の未適用変更があれば停止します。IAM・network・secret ARN の変更は operator の bootstrap で先に適用します。
Docker build → ローカル health → ECR push → digest 固定 → Terraform app plan/apply → ECS revision/image 照合です。
Terraform が task definition と service を管理します。別の workflow で同じ属性を直接変更しません。

共通 module の更新は `main.tf`（v1 移行案件は `preset.tf.json`）の **source の ref** を PR で変更します。
両 root の参照をレビューし、provider の変更が必要なら制約と lock も更新します。
`.terraform.lock.hcl` は provider を固定するためのもので、Git module の ref は root で固定します。
`check` / `container-check` を実行し、bootstrap 済みなら `plan` をレビューします。
foundation に変更があれば更新 branch で operator が bootstrap し、生成設定を同じ PR へ追加します。
マージ後は deploy が app を適用します。Dockerfile・workflow・スクリプトの更新も案件の PR で行います。

native Terraform も直接使えます。app の plan では ECR の immutable image digest を `image_uri` に明示してください。
Git revert は削除した resource やデータを復元しません。復旧中は CI の配置を停止し、state と plan を確認して操作します。
