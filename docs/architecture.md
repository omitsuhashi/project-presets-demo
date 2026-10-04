# 構成と保守方法

このリポジトリは、言語ごとの設定・依存を固定して配布し、利用側にレビュー可能な更新を届けます。Profile の構成、利用側への適用、配布側の公開、AWS インフラをそれぞれの責務として扱います。

## Profile の定義

`profiles/definitions.json` は各 Profile が採用する依存名・用途・設定参照を定義します。依存版は `package.json` / `pyproject.toml` の exact pin が正本です。Dependabot の更新候補もここへ反映します。

`scripts/catalog.py generate` は利用側へ配布する `profiles.json` / `python/profiles.json` と旧 Python 導入用 requirements を生成します。`check` は手動編集や生成漏れを拒否し、公開前の入力検証にも含まれます。

## 利用側 CLI

```text
CLI の引数
    ↓
project: 利用側と配布物の状態を読む
    ↓
plan: 管理対象の差分・衝突・生成内容を計算する
    ↓
preview: 計画の summary を表示する
    ├─ check → manifest・設定・native lock・導入環境を検証
    └─ write/setup → 計画を適用し、必要なら pnpm / uv で同期
```

TypeScript の `scripts/presets/plan.mjs` と Python の `python/project_presets_demo/plan.py` は、渡された snapshot と preset だけで計画を返します。ファイルの読み書き・外部コマンドは実行しません。preview と実適用は同じ計画を使い、管理依存の手動変更、削除、Profile 切替、設定の衝突は適用前に拒否します。

各言語の `project` module が読み取り・適用・検証を実行します。TypeScript は生成した JSON と新規設定を保存します。Python は計画に含む `uv add` で依存を編集し、案件固有の TOML・コメントを保ちます。既存の lint 設定と workflow は利用側が保守します。

書き込みはファイルを stage してから置き換えます。pnpm / uv の失敗まで含む全操作の transaction ではありません。途中失敗の復旧は [更新手順](update.md#5-失敗時適用後の復旧) に従います。

## 配布と版

| 概念 | 意味 | 保存先 |
| --- | --- | --- |
| publication tag | 今回の公開を識別する Git タグ | manifest のトップレベル `tag` |
| preset version | 利用側が採用する各 Profile の版 | manifest の各 `version`、成果物の native version、利用側 marker の `release` |
| artifact | その版が最初に公開された成果物 | manifest の各 `tag` と `asset` |
| 開発環境の版 | 配布元 checkout の package version | ルート `package.json` / `pyproject.toml` |

例えば公開タグ v2.3.0 で Hono の preset version だけが 2.2.1 になることがあります。未変更 Profile は以前の版と artifact を引き継ぎます。利用側 marker の `release` は公開タグから推測せず、選択した Profile の native version と照合します。

`scripts/release_manifest.py` が版・Profile・成果物名の共有契約を定義します。配布側の `release_presets.py` と利用側の `update-consumer.py` は、この module を使います。利用側の更新選択は build 処理に依存しません。

## AWS インフラ

アプリ preset と独立した package / タグで、共通 Terraform module と初回 recipe を配布します。
module の採用版は利用側 root の固定 ref、provider は root の制約と native lock で管理します。

| 資材 | 責務・所有 |
| --- | --- |
| `infra/modules/` | 配布側が継続保守する Terraform module |
| `cli.py` / `scaffold.py` / `config.py` | 初回 `init` と v1 からの所有移行。通常配置・継続更新は担当しない |
| `recipe/scripts/` | 利用側へコピーする bootstrap・配置・検証の見本。コピー後は案件所有 |
| `recipe/*.yml` | 案件内 scripts を実行する検証/配置 workflow の見本 |
| `templates/` | 初回の Dockerfile・起動例。生成後は案件所有 |

v2 は所有 marker、Dockerfile hash、インフラ更新 PR workflow を持ちません。
module source / provider 制約 / Dockerfile / scripts / workflow の変更は利用側でレビューします。
既存案件へ recipe の新版を自動同期しません。通常の配置が配布元の可変 branch や Python package に依存することもありません。

foundation/app の state と operator/CI の権限分離は維持します。state 作成・S3 移行・既存 OIDC・image digest の引継ぎは、
案件所有の bootstrap / deploy recipe に実装します。標準の Terraform / Docker / AWS CLI も直接使えます。
v1 移行では root・module ref・backend・state address を保持し、workflow/scripts と所有ルールだけを変更します。
[導入・保守・移行](infrastructure.md) に具体的な手順があります。

## 変更時の検証

`pnpm run test:plans` は変更計画と catalog の契約を、依存導入やネットワークなしで確認します。`pnpm test` はそれに加えて実際の tarball / wheel の導入・設定保持・変更拒否・lock・更新なし・revert を検証します。CLI module を追加したときは、配布物への同梱と release fingerprint への反映も確認します。

インフラの検証は `infra/check.py` と Terraform module の mock tests を使います。認証なしの検証は実 AWS での配置結果の証明にはなりません。
