# project-presets-demo

**言語・フレームワーク・依存パッケージの版・対応する lint / TypeScript 設定を、構成プリセットとして配布するデモ**です。

利用側は構成を選び、固定版の共有資産を参照します。中央で構成を更新したら、利用側の依存と設定を一つの PR で更新します。業務コードと案件固有の設定は利用側が保守します。

## 選べる構成

| Profile | ランタイム・用途 | 主な依存 | 対応する設定 |
| --- | --- | --- | --- |
| `typescript-node` | Node.js 24 / TypeScript | TypeScript 6.0.3、ESLint 9.39.5、Node.js 型定義 | TypeScript recommended + Node globals、NodeNext / strict |
| `typescript-hono` | Node.js 24 / HTTP API | 上記 + Hono 4.13.12、Node adapter 2.1.3 | Node.js 用 lint / TypeScript 設定 |
| `typescript-next` | Node.js 24 / Next.js App Router | Next.js 16.3.8、React 19.3.0、対応する型定義 | Next.js Core Web Vitals + TypeScript lint、bundler / JSX / strict |
| `python-scripts` | Python 3.12 / スクリプト | Ruff 0.16.10 | 共通 correctness / import / bugbear 設定。print を許可 |

正本は [profiles.json](profiles.json)です。Next.js と `eslint-config-next` は同じ版で揃えます。ESLint 9 と TypeScript 6 の選択は、それぞれ Next.js の plugin と typescript-eslint の対応範囲に合わせています。個々の最新版を組み合わせたことを互換性の証拠にしません。

これらは公開デモの検証対象です。組織で採用する標準やサポート範囲は、利用ケースと保守担当を決めてから定めます。

ESLint 9 は [2026-08-06 に EOL](https://eslint.org/version-support/) となっています。現在の Next.js preset に含まれる React plugin の peer 対応に合わせて、このデモでは 9 を固定しています。本運用の構成に昇格する前に、plugin の現行 ESLint 対応を確認し、保守中のツールを使える組み合わせへ更新する必要があります。

## TypeScript の初回導入

空の npm プロジェクトに、必要な Profile を適用します。Node.js 24 と Git を使います。

```sh
mkdir my-api
cd my-api
npm init -y
npm pkg set type=module

npm install --package-lock-only --allow-git=root --ignore-scripts --save-dev --save-exact \
  'git+https://github.com/omitsuhashi/project-presets-demo.git#v1.0.0' \
  eslint@9.39.5 typescript@6.0.3
npm ci --allow-git=root --ignore-scripts

# まず差分を見る。書き込みは --write を付けた時だけ。
npm exec -- project-presets typescript-hono
npm exec -- project-presets typescript-hono --write

npm install --package-lock-only --allow-git=root --ignore-scripts
npm ci --allow-git=root --ignore-scripts
```

Next.js を選ぶ場合は `typescript-next`、フレームワークを使わない場合は `typescript-node` に置き換えます。フレームワークの依存を runtime dependency、lint と型定義を dev dependency に入れます。

初回に作るファイルは次の四つです。

- `package.json`: Profile が管理する依存を追加。既存の script と無関係な依存を保持。
- `eslint.config.mjs`: 選択した共有 preset を import。
- `tsconfig.json`: 選択した共有 compiler 設定を extends。
- `.project-preset.json`: 選択した Profile、配布版、管理対象の依存と前回の値。

アプリケーションのファイルは利用側で作ります。最小コードは [Hono](examples/hono)、[Next.js](examples/next)、[Node.js](examples/typescript) を参照してください。`npm exec -- eslint .` と `npm exec -- tsc --noEmit` で検査します。

## 利用側の上書き

Hono の `eslint.config.mjs` の例です。

```js
import preset from 'project-presets-demo/hono';

export default [
  ...preset,
  { rules: { '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }] } },
];
```

`tsconfig.json` も `extends` を残して案件固有の `include` 等を追加できます。同じ Profile の更新時は両ファイルを保持し、中央の import / extends 先が更新されます。

適用 CLI は既存の lint / compiler 設定がある未登録プロジェクトでは停止します。既存案件では上の import / extends をレビューして統合し、`--adopt --write` で既存の設定を保持して登録します。管理対象の依存が既にある場合は exact version の差分も先に統合します。手で変更した管理対象 dependency や削除、フレームワークの切替は検出して停止します。フレームワークの切替には業務コードの移行が必要です。

## TypeScript の更新と復旧

新しい配布版を取り込み、**その版の Profile を適用してから lock を作り直す**ことで、フレームワークの版と設定を揃えます。以下の `v1.1.0` は将来その版を公開した後の例です。

```sh
npm install --package-lock-only --allow-git=root --ignore-scripts --save-dev --save-exact \
  'git+https://github.com/omitsuhashi/project-presets-demo.git#v1.1.0'
npm ci --allow-git=root --ignore-scripts
npm exec -- project-presets typescript-hono
npm exec -- project-presets typescript-hono --write
npm install --package-lock-only --allow-git=root --ignore-scripts
npm ci --allow-git=root --ignore-scripts

npm exec -- project-presets typescript-hono --check
npm exec -- eslint .
npm exec -- tsc --noEmit
```

Next.js では `next build` など案件の build / test も通します。`--check` は配布版、Profile 管理の依存、導入状態を確認します。配布 package だけ更新して Profile の適用を忘れた場合は失敗します。

更新 PR には `package.json`、`package-lock.json`、`.project-preset.json` の差分を含めます。復旧はその commit を revert し、戻した lock で `npm ci --allow-git=root --ignore-scripts` を実行します。

## Python の導入・更新

Python の利用側は Git と uv を使います。設定は Git submodule の SHA、tool の版は中央の requirements と利用側の uv lock で管理します。

既存の Git / uv プロジェクトのルートで実行します。

```sh
git submodule add --branch release/v1 \
  https://github.com/omitsuhashi/project-presets-demo.git .project-presets
git -C .project-presets checkout v1.0.0
uv add --dev -r .project-presets/profiles/python-scripts/requirements-dev.txt
```

`pyproject.toml` に追記します。Python の対象版は Profile に合わせ、実際の `requires-python` と runtime も利用側で管理します。

```toml
[tool.ruff]
extend = ".project-presets/python/scripts.toml"
target-version = "py312"
line-length = 100
extend-exclude = [".project-presets"]
```

`.gitmodules`、submodule の SHA、`pyproject.toml`、`uv.lock` を commit し、`uv run --locked ruff check .` を実行します。clone と CI では `git submodule update --init --recursive` が必要です。

更新時は新しいタグを checkout し、再度 `uv add --dev -r ...` を実行します。同じ PR に submodule の SHA と uv の manifest / lock を含めます。復旧は commit を revert し、`git submodule update --init --recursive` と `uv sync --locked` を実行します。

## 更新 PR を受け取る

利用側の `.github/dependabot.yml` に [サンプル](examples/dependabot.yml)を置き、必要な項目を残します。

- TypeScript: 配布 package の更新を候補にし、同じ PR で Profile を適用する。管理対象のフレームワークだけを独立に最新版へ上げない。
- Python: submodule の更新候補を受け取り、同じ PR で requirements を uv に反映する。

Git submodule の Dependabot は新しい SemVer タグを選びません。`release/v1` の commit を追います。配布元はこの branch に検証・リリース済みの互換 commit だけを追加し、利用側の実行は保存済み SHA に固定します。major の採用は別に判断します。

サンプルは更新候補を作る設定です。Profile 適用・lock 更新を PR に追記する工程と、実際の Bot 起動は利用側で確認します。組織ごとの自動適用 Bot は、このデモの CLI / uv 手順を同じ PR で実行する形で追加できます。

## この repository の検証

```sh
npm ci --ignore-scripts
uvx --from ruff==0.16.10 ruff --version
npm run lint
npm run demo:ts
npm run demo:py
npm test
```

`npm test` は一時的な Git 配布元と利用側を作り、次を実行します。

1. preview が書き込まないこと、未知の Profile / フレームワーク切替 / 手動依存変更で停止すること。
2. Hono と Next.js の依存、lint、TypeScript 設定が Profile と一致すること。Hono の HTTP 応答、Next.js の build。
3. 中央の検証用 `v2.0.0` で依存の版と lint ルールを更新し、利用側のコード・設定の上書きが維持されること。
4. npm manifest / lock / Profile 状態と submodule の SHA を戻して復旧できること。

検証用 `v2.0.0` は一時 fixture です。実際の配布元は `v1.0.0` を公開します。

## 新しい構成を追加する時

Profile に exact version の依存、対応 runtime、lint / compiler 設定の参照を追加し、代表アプリで install / lint / typecheck / build / runtime を検証します。対応表を増やすだけでサポート済みとは扱いません。

公開済みタグは差し替えません。既存案件の CI を新たに失敗させるルール、非互換な framework / runtime、managed dependency の削除は major または明示した移行として配布します。変更点、移行、復旧手順は changelog に残します。Framework 移行の codemod、IaC、CI の共有 workflow、開発 image は、それぞれ必要になった時に同じ固定版の参照へ追加できます。

## 仕様の参照先

- [ESLint: Shareable Configs](https://eslint.org/docs/latest/extend/shareable-configs)
- [typescript-eslint: Dependency Versions](https://typescript-eslint.io/users/dependency-versions/)
- [Next.js: ESLint](https://nextjs.org/docs/app/api-reference/config/eslint)
- [Hono: Node.js](https://hono.dev/docs/getting-started/nodejs)
- [npm: allow-git](https://docs.npmjs.com/cli/install/#allow-git)
- [Ruff: Configuration](https://docs.astral.sh/ruff/configuration/)
- [GitHub: Dependabot Versioning Tags](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference#versioning-tags)

MIT License.
