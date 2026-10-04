# 共通 Terraform module と初回 recipe

このディレクトリは、固定 Git ref で再利用する Terraform module と、利用側へ一度コピーする AWS ECS recipe を配布します。
開発中の 2.0.0 は生成後の所有権を利用側へ渡します。公開済み 1.x のタグ・wheel・tools branch は保持します。

- `modules/aws-foundation/`: デモ用ネットワーク、state 保存先、GitHub OIDC とアプリ用 IAM。
- `modules/aws-container-service/`: ECR、ALB、ECS、ログ。network / IAM / image digest を入力する。
- `python/project_presets_infra/recipe/`: 案件所有の scripts・workflow・操作手順。初回生成後は通常の案件コード。
- `python/project_presets_infra/templates/`: 初回の Dockerfile とアプリ起動例。
- `check.py`: wheel の導入、所有移行、root/schema、AWS 操作の mock、コンテナの契約検証。
- `tests/fixtures/v1/`: 既存 address と固定 ref を変えない移行の fixture。

Terraform root の `module.preset.source` を `infra-aws-container-vX.Y.Z` 等の固定 ref にします。
provider は root の制約と `.terraform.lock.hcl` で案件側が保守します。recipe の新版は既存案件へ自動同期しません。
module の更新は参照変更と plan の PR、Dockerfile / workflow / script の更新は案件コードの PR です。

[導入・更新・1.x からの移行](../docs/infrastructure.md) に具体的な手順があります。
生成ツールは `init` のみです。配置に配布側 Python package / reusable workflow / 可変 tools branch は不要です。
既存の foundation/app の resource address と state 分離は維持します。初回 state の作成・移行は明示的な operator 操作です。
