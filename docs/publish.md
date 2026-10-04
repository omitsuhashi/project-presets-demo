# 配布側の更新・公開

依存・共通設定を更新し、検証した成果物を GitHub Release に公開する手順です。npm / PyPI には publish しません。利用側への適用は [更新手順](update.md) に従います。

インフラ用は別 package / 別タグで、[インフラの配布側更新](infrastructure.md#配布側が更新する) に従います。

## 版と公開単位

**テンプレートの版は6つ、公開タグと Release は1回につき1つ**です。`release-manifest.json` を版と配布先の管理元にします。ルートの `package.json` / `pyproject.toml` は配布元の開発環境用です。build 時に各成果物の native version をテンプレート版に設定するため、ルートの版を毎回揃える必要はありません。

| テンプレート | 成果物の例 |
| --- | --- |
| typescript-node | `typescript-node-2.2.0.tgz` |
| typescript-hono | `typescript-hono-2.2.0.tgz` |
| typescript-next | `typescript-next-2.2.0.tgz` |
| python-scripts | `project_presets_demo-2.2.0-1scripts-py3-none-any.whl` |
| python-django | `project_presets_demo-2.2.0-1django-py3-none-any.whl` |
| python-fastapi | `project_presets_demo-2.2.0-1fastapi-py3-none-any.whl` |

v2.2.0 は全テンプレートの 2.2.0 を準備する未公開版です。以後、例えば v2.3.0 の公開で Hono だけが変わると、その版は 2.2.1 になり、残る5つは 2.2.0 のままです。manifest は未変更エントリの版・元のタグ・ファイル名をそのまま引き継ぎます。利用側は `tag` と `asset` から URL を組み立てるので、未変更の URL と lock は変わりません。

Python wheel の `1scripts` 等は標準の wheel build tag で、同じ配布名のテンプレートを識別します。互換性や更新順序はテンプレートの version で判断します。CLI は成果物内のテンプレートと指定 Profile の一致も確認します。

## 依存・設定を更新する

[Dependabot](../.github/dependabot.yml) は npm・uv・GitHub Actions の更新候補を毎週 PR にします。候補 PR のマージだけでは配布物は公開されません。Node.js 24 / npm 12、uv 0.11.7、Python 3.12、Git、GitHub CLI を使います。

```sh
pnpm() { npx --yes --ignore-scripts --package=pnpm@11.28.0 -- pnpm "$@"; }
pnpm install --frozen-lockfile --ignore-scripts
```

| 変更 | 更新する場所 |
| --- | --- |
| TypeScript / ESLint / Hono / Next / React / 型定義 | `profiles.json` の pin、`package.json` の依存または検証用 devDependencies、該当する設定 |
| pnpm | `package.json` の dependencies.pnpm / packageManager、CI と手順書の固定版 |
| Ruff | `pyproject.toml` の依存、`python/profiles.json` の全 Profile、互換用 requirements-dev.txt |
| Django / FastAPI / Uvicorn | `pyproject.toml` の optional-dependencies と `python/profiles.json` の対象 Profile |
| TypeScript 設定 | `typescript/` |
| Python 設定 | `python/project_presets_demo/config/` |
| CLI / 更新処理 | 各 CLI、`scripts/update-consumer.py`、共通 workflow テンプレート |

Next と eslint-config-next は同じ版に揃えます。framework の Python / Node 要件とアプリへの非互換性も確認します。lock の更新には pnpm / uv の通常の操作を使い、文字列置換しません。配布元 lock 自体は利用側にコピーされません。

## 変更したテンプレートだけ版を準備する

依存と設定を編集した後、未使用の次の**公開タグ**を指定します。

```sh
uv run --no-project --python 3.12 python scripts/release_presets.py prepare --tag v2.3.0
```

この処理がテンプレートごとの有効な入力をハッシュで比較し、変更した版だけ patch を上げます。設定は継承先も比較します。Hono の pin は Hono だけ、Node 共通設定は Node / Hono、Django 設定は Django だけ、Ruff 共通設定は Python 全体に反映します。共通 CLI / 更新処理の変更は対応するテンプレートに反映します。文書・テスト・検証専用 CI・配布元 lock の変更だけでは版を上げません。

変更がなければ manifest を書き換えず終了します。タグは作らないでください。互換な機能追加には `--bump minor`、既存 CI を失敗させる lint や非互換な runtime / framework 更新には `--bump major` を指定します。選んだ bump は今回変更したテンプレートに適用されるので、互換性が異なる変更は別の公開に分けます。フレームワークの版の数字だけで互換性を判断しません。

manifest と `CHANGELOG.md` を同じ PR に含め、変更したテンプレート・版・移行作業を明記します。manifest の fingerprint と URL を手で書き換えません。公開済みのテンプレート版と URL は不変です。

## 検証して PR をマージする

```sh
uv lock --check
pnpm run lint
pnpm run demo:ts
pnpm run demo:py
uv run --locked ruff check --config python/base.toml python/project_presets_demo scripts/check-packages.py scripts/update-consumer.py scripts/check-release-routing.py scripts/release_presets.py
pnpm test
uv run --no-project --python 3.12 python scripts/release_presets.py check
git diff --check
```

テストは実際の6つの成果物を build / 導入し、Hono だけの次回公開で残る5つの利用側にファイル変更がないことを確認します。既存の導入・lock・設定保持・手動変更の拒否・アプリ実行・revert も検証します。

変更を commit / push し、PR の CI と変更説明を確認してマージします。互換性を検証できない変更は自動マージしません。

## 検証した commit を1つのタグで公開する

PR のマージ後、main の CI 成功を確認してから実行します。ここが実際の公開操作です。

```sh
git switch main
git pull --ff-only
PRESET_TAG=$(node -p "JSON.parse(require('node:fs').readFileSync('release-manifest.json')).tag")
uv run --no-project --python 3.12 python scripts/release_presets.py check --tag "$PRESET_TAG"
git tag "$PRESET_TAG"
git push origin "$PRESET_TAG"
```

[release workflow](../.github/workflows/release.yml) がタグと manifest と入力ハッシュを照合し、共通の検証を1回実行します。今回のタグを持つテンプレートだけ build し、完全な `release-manifest.json` と `SHA256SUMS` を draft Release に添付してから公開します。未変更成果物は再 build / 再添付しません。以前の Release を残してください。

```sh
gh release view "$PRESET_TAG" --repo omitsuhashi/project-presets-demo
gh release download "$PRESET_TAG" --repo omitsuhashi/project-presets-demo --dir "/tmp/project-presets-$PRESET_TAG"
(cd "/tmp/project-presets-$PRESET_TAG" && shasum -a 256 -c SHA256SUMS)
```

Actions の成功・公開された asset を確認し、manifest の URL で対象テンプレートの導入・更新・check とアプリテストを行います。Release 全体の latest 表示は更新選択に使いません。既存 workflow の移行は [更新手順](update.md#テンプレート別リリースへの移行) に従います。

## 公開に失敗した時

タグを push しただけでは公開成功とは見なしません。Actions と `gh release view` を確認します。未公開 draft が残った時は draft であることを確認し、取り除いて同じ commit の workflow を再実行できます。ソース修正が必要なら新しい版を準備します。公開済みタグ・成果物は差し替えません。問題があれば新しい修正版を公開し、利用側は更新または更新 PR の revert で復旧します。
