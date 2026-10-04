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

アプリ preset と独立した package / タグを使います。Terraform module の参照先は `infra/modules/` です。

| Module | 責務 |
| --- | --- |
| `cli.py` | コマンドの引数と処理の選択 |
| `scaffold.py` | Terraform root・Dockerfile・workflow の生成 |
| `update.py` | 管理参照と Docker template の更新・衝突検出 |
| `bootstrap.py` | operator による初期設定と state の移行 |
| `deploy.py` | コンテナ検証・ECR push・digest を指定した配置・ECS revision の確認 |
| `native.py` | process 実行、Terraform state、AWS account、foundation の変更検出 |
| `config.py` | Profile・固定 provider・module source の定義 |

AWS の初期設定と通常配置の権限・確認手順は [インフラ手順](infrastructure.md) に従います。

## 変更時の検証

`pnpm run test:plans` は変更計画と catalog の契約を、依存導入やネットワークなしで確認します。`pnpm test` はそれに加えて実際の tarball / wheel の導入・設定保持・変更拒否・lock・更新なし・revert を検証します。CLI module を追加したときは、配布物への同梱と release fingerprint への反映も確認します。

インフラの検証は `infra/check.py` と Terraform module の mock tests を使います。認証なしの検証は実 AWS での配置結果の証明にはなりません。
